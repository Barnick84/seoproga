# services/miratext_client.py
import time
from typing import Dict, List, Optional

import requests

from config import Config


class MiratextClient:
    BASE_URL = "https://miratext.ru/api2"

    def __init__(
        self,
        api_key: Optional[str] = None,
    ):
        self.api_key = api_key or Config.MIRATEXT_API_KEY
        self.region = Config.MIRATEXT_REGION
        self.max_wait = Config.MIRATEXT_MAX_WAIT
        self.poll_interval = Config.MIRATEXT_POLL_INTERVAL
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict:
        url = f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("timeout", 30)
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def submit_analysis(self, text: str, keywords: List[str]) -> str:
        payload = {
            "api_key": self.api_key,
            "check_type": "text",
            "text": text[:50000],
            "keywords_search": {
                "keywords": ",".join(keywords),
                "search_type": "yandex",
                "region_id": self.region,
            },
            "language": "ru",
        }
        result = self._request("POST", "/article/seoAnalizText", json=payload)
        if result.get("status") == "accepted":
            return result["data"]["task_id"]
        raise ValueError(f"Miratext error: {result.get('error')}")

    def get_result(self, task_id: str) -> Dict:
        start = time.time()
        while time.time() - start < self.max_wait:
            status = self._request("GET", f"/article/status/{task_id}")
            st = status.get("status")

            if st == "done":
                return status.get("data", {})
            if st == "error":
                raise RuntimeError(f"Miratext analysis error: {status.get('error')}")

            time.sleep(self.poll_interval)
        raise TimeoutError("Miratext analysis timeout")

    def analyze(self, text: str, keywords: List[str]) -> Dict:
        task_id = self.submit_analysis(text, keywords)
        raw = self.get_result(task_id)
        return self._parse_recommendations(raw, keywords)

    def _parse_recommendations(self, raw: Dict, target_keywords: List[str]) -> Dict:
        tz = raw.get("tz", {})
        recommendations = []
        target_lower = {k.lower() for k in target_keywords}

        for item in tz.get("keywordsAll", []):
            kw = item.get("word", "").strip().lower()
            if kw in target_lower:
                rec = item.get("recomended", 0)
                cur = item.get("my_count", 0)
                recommendations.append(
                    {
                        "keyword": item.get("word"),
                        "recommended": rec,
                        "current": cur,
                        "need_to_add": max(0, rec - cur),
                        "density": item.get("density", 0.0),
                    }
                )

        return {
            "keywords": recommendations,
            "total_words": tz.get("wordsCount", 0),
            "status": raw.get("status"),
        }
