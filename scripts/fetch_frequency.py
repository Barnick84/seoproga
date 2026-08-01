# nodejs-app/scripts/fetch_frequency.py
import json
import sys
import time

import requests

from utils.bootstrap import bootstrap
from utils.helpers import safe_print

bootstrap()


from config import Config
from services.task_manager import TaskManager

WORDSTAT_URL = "https://xmlriver.com/wordstat/new/json"


def fetch_wordstat(query: str, device: str, region: str) -> dict | None:
    params = {
        "query": query,
        "key": Config.XMLRIVER_KEY,
        "user": Config.XMLRIVER_USER,
        "pagetype": "history",
    }
    if device:
        params["device"] = device
    if region:
        params["regions"] = region
    try:
        resp = requests.get(WORDSTAT_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"WARN: API error for '{query}': {e}", file=sys.stderr)
        return None


def fetch_frequency_task(
    domain: str,
    user_id: int,
    device: str = "",
    region: str = "",
    mode: str = "all",
    min_freq: int = 10,
    task_id: int = 0,
    cluster_id: int = 0,
) -> dict:
    domain = domain.lower().strip()
    if domain.startswith("http://"):
        domain = domain[7:]
    elif domain.startswith("https://"):
        domain = domain[8:]
    domain = domain.rstrip("/")

    tm = TaskManager(task_id)
    tm.set_status("running")

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        query_sql = "SELECT id, query, clustered, frequency FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND is_right_column = 0"
        params = [user_id, domain]

        if mode == "missing":
            query_sql += " AND (frequency IS NULL OR frequency = 0)"

        if cluster_id > 0:
            query_sql += " AND clustered = %s"
            params.append(cluster_id)

        cur.execute(query_sql, tuple(params))
        keywords = cur.fetchall()

        if not keywords:
            tm.set_status("completed", "No keywords found")
            return {"success": True, "processed": 0}

        # BUG-5 FIX: Load minus words ONCE before the loop
        cur.execute(
            "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 1",
            (user_id, domain),
        )
        minus_words = {r["query"].lower() for r in cur.fetchall()}

        total = len(keywords)
        processed = 0
        updated = 0

        for kw in keywords:
            processed += 1
            progress = int((processed / total) * 100)
            tm.update_progress(
                progress,
                {"current_query": kw["query"], "processed": processed, "total": total},
            )

            data = fetch_wordstat(kw["query"], device, region)
            if data is None:
                time.sleep(Config.XMLRIVER_REQUEST_DELAY)
                continue

            freq = 0
            try:
                popular = data["table"]["tableData"]["popular"]
                for item in popular:
                    if item.get("text", "").strip().lower() == kw["query"].lower():
                        freq = int(item.get("value", 0))
                        break
            except Exception:
                freq = int(data.get("totalValue", 0))

            if freq <= min_freq:
                cur.execute(
                    "UPDATE yandex_queries SET frequency = %s, minus_word = 1, clustered = 0 WHERE id = %s",
                    (freq, kw["id"]),
                )
            else:
                cur.execute(
                    "UPDATE yandex_queries SET frequency = %s WHERE id = %s",
                    (freq, kw["id"]),
                )

            # LSI Collection
            if kw["clustered"] > 0:
                lsi_candidates = []
                try:
                    associations = (
                        data.get("table", {}).get("tableData", {}).get("associations", [])
                    )
                    for item in associations:
                        text = item.get("text", "").strip().lower()
                        val = int(item.get("value", 0))
                        if text and text != kw["query"].lower():
                            lsi_candidates.append((text, val))

                    popular = data.get("table", {}).get("tableData", {}).get("popular", [])
                    for item in popular:
                        text = item.get("text", "").strip().lower()
                        val = int(item.get("value", 0))
                        if text and text != kw["query"].lower():
                            lsi_candidates.append((text, val))
                except Exception as e:
                    safe_print(
                        f"WARN: Error parsing LSI for '{kw['query']}': {e}",
                        file=sys.stderr,
                    )

                for lsi_text, lsi_val in lsi_candidates:
                    if lsi_text in minus_words:
                        continue
                    try:
                        cur.execute(
                            """
                            INSERT INTO cluster_lsi (user_id, site_url, cluster_id, keyword, frequency)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE frequency = GREATEST(frequency, VALUES(frequency))
                            """,
                            (user_id, domain, kw["clustered"], lsi_text, lsi_val),
                        )
                    except Exception as e:
                        safe_print(f"WARN: Error saving LSI '{lsi_text}': {e}", file=sys.stderr)

            updated += 1
            time.sleep(Config.XMLRIVER_REQUEST_DELAY)

        conn.commit()
        result = {"success": True, "processed": processed, "updated": updated}
        tm.set_result(result)
        tm.set_status("completed")
        return result

    except Exception as e:
        conn.rollback()
        tm.set_status("failed", str(e))
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def main():
    if len(sys.argv) < 3:
        safe_print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: fetch_frequency.py <domain> <user_id> ...",
                }
            )
        )
        sys.exit(1)

    domain = sys.argv[1]
    user_id = int(sys.argv[2])
    device = sys.argv[3].strip() if len(sys.argv) > 3 else ""
    region = sys.argv[4].strip() if len(sys.argv) > 4 else ""
    mode = sys.argv[5].strip() if len(sys.argv) > 5 else "all"
    min_freq = int(sys.argv[6]) if len(sys.argv) > 6 else 10
    task_id = int(sys.argv[7]) if len(sys.argv) > 7 else 0
    cluster_id = int(sys.argv[8]) if len(sys.argv) > 8 else 0

    result = fetch_frequency_task(
        domain, user_id, device, region, mode, min_freq, task_id, cluster_id
    )
    safe_print(json.dumps(result))


if __name__ == "__main__":
    main()
