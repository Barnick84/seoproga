# services/xmlriver_client.py
import requests
import xmltodict
import time
from typing import Optional
from config import Config
from utils.helpers import clean_url
from services.cache import SERPCache


class XmlriverClient:
    def __init__(
        self,
        cache: Optional[SERPCache] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        self.cache = cache or SERPCache()
        self.base_url_yandex = "https://xmlriver.com/search_yandex/xml"
        self.base_url_google = "https://xmlriver.com/search_google/xml"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_base_url(self, engine: str) -> str:
        return self.base_url_yandex if engine == "yandex" else self.base_url_google

    def _is_retry_needed(self, data: dict) -> bool:
        if "yandexsearch" not in data:
            return False
        yandexsearch = data.get("yandexsearch", {})
        response = yandexsearch.get("response", {})
        error = response.get("error", {})
        if error:
            error_code = error.get("@code")
            error_text = error.get("#text", "")

            if error_code == "500" and "перезапрос" in error_text.lower():
                return True
        return False

    def fetch_serp(
        self,
        keyword: str,
        engine: str = None,
        region: int = None,
        device: str = "desktop",
        top_n: int = None,
        page: int = 0,
        use_cache: bool = True,
        retries: int = None,
    ) -> list[str]:
        engine = engine or Config.XMLRIVER_ENGINE
        
        # Default region for Google is Russia (225) if not specified
        if engine == "google" and region is None:
            region = 225
        else:
            region = region or Config.XMLRIVER_REGION
            
        top_n = top_n or Config.SERP_TOP_N
        retries = retries or self.max_retries

        if use_cache:
            # Cache key includes engine, region, device, and page
            cache_key = f"{keyword}|{engine}|{region}|{device}|{page}"
            cached = self.cache.get(cache_key, engine, region) # Wait, cache.get also needs updated key logic
            if cached:
                return cached

        base_url = self._get_base_url(engine)
        params = {
            "user": Config.XMLRIVER_USER,
            "key": Config.XMLRIVER_KEY,
            "query": keyword.replace("&", "%26"),
            "groupby": top_n,
            "page": page,
            "device": device,
        }
        
        if engine == "yandex":
            params["lr"] = region
            params["domain"] = "ru"
        else:
            # Google often uses loc or country. We'll try loc for region ID.
            # And domain should be 'ru' if we are in Russia.
            params["loc"] = region
            params["domain"] = "ru" if region in [225, 213, 2, 1] else "com"
        
        # Google specific adjustments if needed
        params["lang"] = "ru"

        last_error = None
        for attempt in range(retries):
            try:
                response = requests.get(base_url, params=params, timeout=60)
                response.raise_for_status()

                data = xmltodict.parse(response.content)


                # Check for 500 error requiring retry
                if self._is_retry_needed(data):
                    if attempt < retries - 1:

                        time.sleep(5)
                        continue
                    return []

                if "yandexsearch" in data:
                    pass
                urls = self._parse_xmlriver_response(data)


                if use_cache and urls:
                    cache_key = f"{keyword}|{engine}|{region}|{device}|{page}"
                    self.cache.set(cache_key, urls, engine, region)

                return urls

            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                pass
                return []

        return []

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
