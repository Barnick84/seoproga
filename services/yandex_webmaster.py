# services/yandex_webmaster.py
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List

import requests

from config import Config

logger = logging.getLogger(__name__)


class YandexWebmasterClient:
    BASE_URL = "https://api.webmaster.yandex.net/v4"

    def __init__(self, token: str, user_id: int):
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}
        )
        self._timeout = 30
        self.user_id = user_id

    def _get_user_id(self) -> str:
        resp = self.session.get(f"{self.BASE_URL}/user", timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()["user_id"]

    def list_hosts(self) -> List[Dict]:
        y_user_id = self._get_user_id()
        resp = self.session.get(f"{self.BASE_URL}/user/{y_user_id}/hosts", timeout=self._timeout)
        resp.raise_for_status()
        return resp.json().get("hosts", [])

    def _normalize_url(self, url: str) -> str:
        url = url.lower().strip()
        for prefix in ("https://", "http://", "https:", "http:"):
            if url.startswith(prefix):
                url = url[len(prefix) :]
        url = url.rstrip("/")
        if url.endswith(":443"):
            url = url[:-4]
        elif url.endswith(":80"):
            url = url[:-3]

        # Always use Unicode for comparison
        try:
            if url.startswith("xn--"):
                url = url.encode("ascii").decode("idna")
        except (UnicodeError, ValueError):
            pass
        return url

    def _get_host_id(self, site_url: str, user_id: str) -> str:
        site = self._normalize_url(site_url)
        site_no_www = site[4:] if site.startswith("www.") else site

        hosts_data = self.list_hosts()
        for host in hosts_data:
            host_id_normalized = self._normalize_url(host["host_id"])
            host_no_www = (
                host_id_normalized[4:]
                if host_id_normalized.startswith("www.")
                else host_id_normalized
            )
            if site == host_id_normalized or site_no_www == host_no_www:
                return host["host_id"]
        raise ValueError(f"Сайт {site_url} не найден в Вебмастере")

    def _extract_query_data(self, q: Dict) -> Dict:
        q_text = q.get("query_text") or q.get("query") or ""
        indicators = q.get("indicators") or {}

        shows = q.get("shows")
        if shows is None:
            shows = q.get("hits")
        if shows is None:
            shows = indicators.get("TOTAL_SHOWS", 0)

        clicks = q.get("clicks")
        if clicks is None:
            clicks = indicators.get("TOTAL_CLICKS", 0)

        avg_pos = q.get("avg_position")
        if avg_pos is None or avg_pos == 0:
            avg_pos = (
                indicators.get("AVG_SHOW_POSITION")
                or indicators.get("AVG_CLICK_POSITION")
                or 0.0
            )

        ctr = q.get("ctr")
        if ctr is None:
            ctr = indicators.get("CTR") or (
                round(float(clicks) / float(shows), 4) if shows and float(shows) > 0 else 0.0
            )

        return {
            "query_text": q_text,
            "shows": int(shows or 0),
            "clicks": int(clicks or 0),
            "ctr": float(ctr or 0.0),
            "avg_position": float(avg_pos or 0.0),
        }

    def fetch_queries_recent(self, site_url: str) -> List[Dict]:
        y_user_id = self._get_user_id()
        host_id = self._get_host_id(site_url, y_user_id)

        normalized_site_url = self._normalize_url(site_url)

        end_date = datetime.now() - timedelta(days=2)
        start_date = end_date - timedelta(days=30)

        all_queries_dict = {}

        endpoints = [
            "/search-queries/all/with-data",
            "/search-queries/popular",
        ]

        for endpoint_path in endpoints:
            for indicator in ["TOTAL_SHOWS", "TOTAL_CLICKS"]:
                params = {
                    "query_indicator": indicator,
                    "order_by": indicator,
                    "limit": 500,
                    "date_from": start_date.strftime("%Y-%m-%d"),
                    "date_to": end_date.strftime("%Y-%m-%d"),
                }

                url = f"{self.BASE_URL}/user/{y_user_id}/hosts/{host_id}{endpoint_path}"
                try:
                    resp = self.session.get(url, params=params, timeout=self._timeout)
                    if resp.status_code == 200:
                        data = resp.json()
                        queries = data.get("queries", [])
                        for q in queries:
                            parsed = self._extract_query_data(q)
                            q_text = parsed["query_text"]
                            if q_text:
                                if q_text not in all_queries_dict:
                                    parsed["site_url"] = normalized_site_url
                                    parsed["period_from"] = params["date_from"]
                                    parsed["period_to"] = params["date_to"]
                                    all_queries_dict[q_text] = parsed
                                else:
                                    existing = all_queries_dict[q_text]
                                    existing["shows"] = max(existing["shows"], parsed["shows"])
                                    existing["clicks"] = max(existing["clicks"], parsed["clicks"])
                                    if parsed["avg_position"] > 0:
                                        existing["avg_position"] = parsed["avg_position"]
                except Exception as e:
                    logger.warning(
                        "Fetch Yandex queries endpoint %s indicator %s error: %s",
                        endpoint_path,
                        indicator,
                        e,
                    )

        return list(all_queries_dict.values())

    def _get_position_rates(self) -> Dict[str, float]:
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT `key`, `value` FROM settings WHERE `key` IN ('position_new_rate', 'position_step_rate')"
            )
            rows = cur.fetchall()
            settings = {row["key"]: float(row["value"]) for row in rows}
            return {
                "new": settings.get("position_new_rate", 0.25),
                "step": settings.get("position_step_rate", 0.05),
            }
        except Exception as e:
            logger.warning("Failed to load position rates from settings, using defaults: %s", e)
            return {"new": 0.25, "step": 0.05}
        finally:
            conn.close()

    def calculate_position_cost(self, pos: float, step_rate: float) -> float:
        if not pos or pos <= 0:
            return step_rate  # Minimum step cost if pos is missing
        return math.ceil(pos / 10) * step_rate

    def save_queries_to_db(self, queries: List[Dict]) -> int:
        if not queries:
            return 0

        added = 0
        new_cost = 0.0
        total_cost = 0.0
        rates = self._get_position_rates()
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            site_url = queries[0].get("site_url", "")

            # PERF-5 FIX: Load all existing queries for this site in ONE SELECT
            cur.execute(
                "SELECT id, query FROM yandex_queries WHERE user_id = %s AND site_url = %s",
                (self.user_id, site_url),
            )
            existing = {row["query"]: row["id"] for row in cur.fetchall()}

            for q in queries:
                q_text = q.get("query_text", q.get("query", ""))
                avg_pos = q.get("avg_position", 0.0)
                q_site_url = q.get("site_url", site_url)

                if q_text in existing:
                    total_cost += self.calculate_position_cost(avg_pos, rates["step"])
                    cur.execute(
                        """
                        UPDATE yandex_queries SET
                            hits = %s, clicks = %s, ctr = %s, avg_position = %s,
                            fetched_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (
                            q.get("shows", q.get("hits", 0)),
                            q.get("clicks", 0),
                            q.get("ctr", 0.0),
                            avg_pos,
                            existing[q_text],
                        ),
                    )
                else:
                    new_cost += rates["new"]
                    total_cost += rates["new"]
                    cur.execute(
                        """
                        INSERT INTO yandex_queries
                        (user_id, site_url, query, period_from, period_to, hits, clicks, ctr, avg_position, minus_word, clustered)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0)
                        """,
                        (
                            self.user_id,
                            q_site_url,
                            q_text,
                            q.get("period_from", ""),
                            q.get("period_to", ""),
                            q.get("shows", q.get("hits", 0)),
                            q.get("clicks", 0),
                            q.get("ctr", 0.0),
                            avg_pos,
                        ),
                    )
                    existing[q_text] = True
                    added += 1

            if new_cost > 0:
                cur.execute(
                    "UPDATE users SET balance = balance - %s WHERE id = %s",
                    (new_cost, self.user_id),
                )
                cur.execute(
                    "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                    (
                        self.user_id,
                        new_cost,
                        f"Сбор позиций ({added} новых зап.) для {site_url}",
                        "charge",
                    ),
                )

            conn.commit()
            return added
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_unique_queries_for_clustering(self, site_url: str) -> List[str]:
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 ORDER BY query",
                (self.user_id, site_url),
            )
            return [row["query"] for row in cur.fetchall()]
        finally:
            conn.close()
