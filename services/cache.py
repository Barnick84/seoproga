# services/cache.py
import json
import logging
from datetime import datetime, timedelta

from config import Config

logger = logging.getLogger(__name__)


class SERPCache:
    def __init__(self):
        self.ttl = timedelta(days=Config.CACHE_TTL_DAYS)
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            self._conn = Config.get_conn()
        elif hasattr(self._conn, "ping"):
            try:
                self._conn.ping(reconnect=True)
            except Exception as e:
                logger.warning("SERPCache connection ping failed, reconnecting lazily: %s", e)
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = Config.get_conn()
        return self._conn

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.debug("SERPCache close ignored error: %s", e)
            self._conn = None

    def _make_key(self, keyword: str, engine: str, region: int) -> str:
        return f"{keyword}|{engine}|{region}"

    def get(self, cache_key: str, engine: str = "", region: int = 0) -> list[str] | None:
        key = cache_key if "|" in cache_key else self._make_key(cache_key, engine, region)
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT urls, fetched_at FROM serp_cache WHERE cache_key=%s", (key,))
        row = cur.fetchone()
        if row:
            urls, fetched = row["urls"], row["fetched_at"]
            if datetime.now() - fetched < self.ttl:
                return json.loads(urls)
        return None

    def set(self, cache_key: str, urls: list[str], engine: str = "", region: int = 0) -> None:
        key = cache_key if "|" in cache_key else self._make_key(cache_key, engine, region)
        conn = self._get_conn()
        cur = conn.cursor()
        urls_json = json.dumps(urls)
        now = datetime.now()
        if Config.DB_TYPE == "postgresql":
            cur.execute(
                "INSERT INTO serp_cache (cache_key, urls, fetched_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (cache_key) DO UPDATE SET urls = EXCLUDED.urls, fetched_at = EXCLUDED.fetched_at",
                (key, urls_json, now),
            )
        else:
            cur.execute(
                "INSERT INTO serp_cache (cache_key, urls, fetched_at) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE urls = VALUES(urls), fetched_at = VALUES(fetched_at)",
                (key, urls_json, now),
            )
        conn.commit()
