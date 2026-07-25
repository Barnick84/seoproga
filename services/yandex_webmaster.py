# services/yandex_webmaster.py
import math
from datetime import datetime, timedelta
from typing import Dict, List

import requests

from config import Config


class YandexWebmasterClient:
    BASE_URL = "https://api.webmaster.yandex.net/v4"

    def __init__(self, token: str, user_id: int):
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}
        )
        self.user_id = user_id

    def _get_user_id(self) -> str:
        resp = self.session.get(f"{self.BASE_URL}/user")
        resp.raise_for_status()
        return resp.json()["user_id"]

    def list_hosts(self) -> List[Dict]:
        y_user_id = self._get_user_id()
        resp = self.session.get(f"{self.BASE_URL}/user/{y_user_id}/hosts")
        resp.raise_for_status()
        return resp.json().get("hosts", [])

    def _normalize_url(self, url: str) -> str:
        url = url.lower().strip()
        for prefix in ("https://", "http://", "https:", "http:"):
            if url.startswith(prefix):
                url = url[len(prefix) :]
        return url.rstrip("/")

    def _get_host_id(self, site_url: str, user_id: str) -> str:
        site = self._normalize_url(site_url)
        try:
            site = site.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            pass

        hosts_data = self.list_hosts()
        for host in hosts_data:
            host_id = self._normalize_url(host["host_id"])
            try:
                host_id = host_id.encode("idna").decode("ascii")
            except (UnicodeError, ValueError):
                pass
            if site == host_id:
                return host["host_id"]
        raise ValueError(f"Сайт {site_url} не найден в Вебмастере")

    def fetch_queries_recent(self, site_url: str) -> List[Dict]:
        y_user_id = self._get_user_id()
        host_id = self._get_host_id(site_url, y_user_id)

        site_url = self._normalize_url(site_url)

        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)

        params = {
            "order_by": "TOTAL_CLICKS",
            "limit": 500,
            "date_from": start_date.strftime("%Y-%m-%d"),
            "date_to": end_date.strftime("%Y-%m-%d"),
        }

        url = f"{self.BASE_URL}/user/{y_user_id}/hosts/{host_id}/search-queries/popular"
        resp = self.session.get(url, params=params)

        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()

        queries = data.get("queries", [])
        for q in queries:
            q["site_url"] = site_url
            q["period_from"] = params["date_from"]
            q["period_to"] = params["date_to"]

        return queries

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
        except Exception:
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
