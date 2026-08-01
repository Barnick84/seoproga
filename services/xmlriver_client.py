# services/xmlriver_client.py
import logging
import random
import time
from typing import Optional

import requests
import xmltodict

from config import Config
from services.cache import SERPCache
from utils.helpers import clean_url

logger = logging.getLogger(__name__)


class XmlriverRetryableError(Exception):
    """Raised when the XMLRiver API reports a retryable error."""

    def __init__(self, code: str, text: str | None):
        super().__init__(f"XMLRiver retryable error {code}: {text}")
        self.code = code
        self.text = text


class XmlriverClient:
    def __init__(
        self,
        cache: Optional[SERPCache] = None,
        max_retries: int = 5,
        retry_delay: float = 2.0,
    ):
        self.cache = cache or SERPCache()
        self.base_url_yandex = "https://xmlriver.com/search_yandex/xml"
        self.base_url_google = "https://xmlriver.com/search_google/xml"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_request: float = 0.0
        self.min_delay: float = Config.XMLRIVER_REQUEST_DELAY
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _get_base_url(self, engine: str) -> str:
        return self.base_url_yandex if engine == "yandex" else self.base_url_google

    def _get_error_info(self, data: dict) -> tuple[str | None, str | None]:
        root = data.get("yandexsearch") or data.get("googlesearch")
        if not root:
            return None, None
        response = root.get("response", {})
        error = response.get("error", {})
        if error:
            return error.get("@code"), error.get("#text", "")
        return None, None

    def _is_retry_needed(self, data: dict) -> bool:
        error_code, error_text = self._get_error_info(data)
        if not error_code:
            return False
        if error_code == "500" and error_text and "перезапрос" in error_text.lower():
            return True
        if error_code == "111":
            return True
        return False

    def _resolve_request(
        self,
        engine: str | None,
        region: int | None,
        top_n: int | None,
        retries: int | None,
    ) -> tuple[str, int, int, int]:
        engine = engine or Config.XMLRIVER_ENGINE
        if engine == "google" and region is None:
            region = 225
        else:
            region = region or Config.XMLRIVER_REGION
        return engine, region, top_n or Config.SERP_TOP_N, retries or self.max_retries

    def _build_params(
        self,
        keyword: str,
        engine: str,
        region: int,
        device: str,
        top_n: int,
        page: int,
    ) -> dict:
        params = {
            "user": Config.XMLRIVER_USER,
            "key": Config.XMLRIVER_KEY,
            "query": keyword,
            "groupby": top_n,
            "page": page,
            "device": device,
        }
        if engine == "yandex":
            params["lr"] = region
            params["domain"] = "ru"
        else:
            params["loc"] = region
            params["domain"] = "ru" if region in [225, 213, 2, 1] else "com"
        params["lang"] = "ru"
        return params

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()

    def _sleep_for_retry(self, error_code: str, attempt: int, retries: int) -> None:
        if error_code == "111":
            wait = min(30, 10 * (attempt + 1)) * random.uniform(0.8, 1.2)
            logger.warning(
                "XMLRiver: нет свободных каналов (111), попытка %s/%s, жду %ss...",
                attempt + 1,
                retries,
                round(wait, 1),
            )
            time.sleep(wait)
        else:
            time.sleep(5 * random.uniform(0.8, 1.2))

    def _cache_key(
        self, keyword: str, engine: str, region: int, device: str, page: int, top_n: int
    ) -> str:
        return f"{keyword}|{engine}|{region}|{device}|{page}|{top_n}"

    def _execute_request(self, base_url: str, params: dict) -> list[str]:
        response = self.session.get(base_url, params=params, timeout=60)
        response.raise_for_status()
        data = xmltodict.parse(response.content)

        error_code, error_text = self._get_error_info(data)
        if error_code:
            if self._is_retry_needed(data):
                raise XmlriverRetryableError(error_code, error_text)
            raise ValueError(f"XMLRiver Fatal Error {error_code}: {error_text}")
        return self._parse_xmlriver_response(data)

    def _fetch_with_retries(self, base_url: str, params: dict, retries: int) -> list[str]:
        last_error = None
        for attempt in range(retries):
            try:
                return self._execute_request(base_url, params)
            except XmlriverRetryableError as e:
                if attempt < retries - 1:
                    self._sleep_for_retry(e.code, attempt, retries)
                    continue
                raise Exception(f"XMLRiver: исчерпаны попытки, ошибка {e.code}: {e.text}") from e
            except ValueError as e:
                logger.error("XMLRiver: фатальная ошибка: %s", e)
                raise
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(self.retry_delay * random.uniform(0.8, 1.2))
                    continue
                logger.error("XMLRiver: исключение при запросе: %s", e)
                raise

        if last_error:
            raise last_error
        return []

    def fetch_serp(
        self,
        keyword: str,
        engine: str | None = None,
        region: int | None = None,
        device: str = "desktop",
        top_n: int | None = None,
        page: int = 0,
        use_cache: bool = True,
        retries: int | None = None,
    ) -> list[str]:
        engine, region, top_n, retries = self._resolve_request(engine, region, top_n, retries)

        if use_cache:
            cache_key = self._cache_key(keyword, engine, region, device, page, top_n)
            cached = self.cache.get(cache_key, engine, region)
            if cached:
                return cached

        self._throttle()

        base_url = self._get_base_url(engine)
        params = self._build_params(keyword, engine, region, device, top_n, page)

        urls = self._fetch_with_retries(base_url, params, retries)
        if use_cache and urls:
            cache_key = self._cache_key(keyword, engine, region, device, page, top_n)
            self.cache.set(cache_key, urls, engine, region)
        return urls

    def _parse_xmlriver_response(self, data: dict) -> list[str]:
        urls = []

        # Handle both yandexsearch and googlesearch roots
        root = data.get("yandexsearch") or data.get("googlesearch")
        if not root:
            return []

        response = root.get("response", {})
        results = response.get("results", {})
        grouping = results.get("grouping", {})
        groups = grouping.get("group", [])

        if isinstance(groups, dict):
            groups = [groups]

        for group in groups:
            docs = group.get("doc", [])

            if isinstance(docs, dict):
                docs = [docs]

            for doc in docs:
                content_type = doc.get("contenttype")

                if content_type == "organic" or content_type is None:
                    url = doc.get("url", "")
                    if url:
                        cleaned = clean_url(url)
                        if cleaned and cleaned not in urls:
                            urls.append(cleaned)

        return urls
