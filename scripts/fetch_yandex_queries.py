# nodejs-app/scripts/fetch_yandex_queries.py
import sys
import os
import json

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.yandex_webmaster import YandexWebmasterClient


def fetch_yandex_queries_task(domain: str, user_id: int) -> dict:
    token = None
    try:
        conn = Config.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT yandex_token FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row and row["yandex_token"]:
            token = row["yandex_token"]
        conn.close()
    except Exception:
        pass

    if not token:
        token = os.getenv("YANDEX_OAUTH_TOKEN")

    if not token:
        return {"success": False, "error": "Yandex token not found"}

    try:
        client = YandexWebmasterClient(token, user_id)
        queries = client.fetch_queries_recent(domain)

        if not queries:
            return {"success": True, "message": "No queries found", "added": 0}

        added = client.save_queries_to_db(queries)
        return {
            "success": True,
            "message": f"Successfully fetched {len(queries)} queries",
            "added": added,
        }
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        return {"success": False, "error": error_msg}


def main():
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: fetch_yandex_queries.py <domain> <user_id>",
                }
            )
        )
        return

    domain = sys.argv[1]
    user_id = int(sys.argv[2])
    
    result = fetch_yandex_queries_task(domain, user_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
