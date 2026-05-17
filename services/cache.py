# services/cache.py
import json
from datetime import datetime, timedelta
from config import Config

class SERPCache:
    def __init__(self):
        self.ttl = timedelta(days=Config.CACHE_TTL_DAYS)

    def _make_key(self, keyword: str, engine: str, region: int) -> str:
        return f"{keyword}|{engine}|{region}"

    def get(self, cache_key: str, engine: str = "", region: int = 0) -> list[str] | None:
        key = cache_key if "|" in cache_key else self._make_key(cache_key, engine, region)
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT urls, fetched_at FROM serp_cache WHERE cache_key=%s", (key,)
            )
            row = cur.fetchone()
            if row:
                urls, fetched = row['urls'], row['fetched_at']
                if datetime.now() - fetched < self.ttl:
                    return json.loads(urls)
        finally:
            conn.close()
        return None

    def set(self, cache_key: str, urls: list[str], engine: str = "", region: int = 0):
        key = cache_key if "|" in cache_key else self._make_key(cache_key, engine, region)
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO serp_cache (cache_key, urls, fetched_at) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE urls=%s, fetched_at=%s",
                (key, json.dumps(urls), datetime.now(), json.dumps(urls), datetime.now()),
            )
        finally:
            conn.close()
