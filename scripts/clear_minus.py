# scripts/clear_minus.py
import sys
import os
import json

from utils.bootstrap import bootstrap

bootstrap()

from config import Config


def clear_minus_words(user_id, domain):
    if not user_id or not domain:
        return {"success": False, "error": "Missing parameters"}

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "UPDATE yandex_queries SET minus_word = 0 WHERE user_id = %s AND site_url = %s",
            (user_id, domain),
        )
        conn.commit()
        count = cur.rowcount
        return {"success": True, "cleared": count}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {"success": False, "error": "Usage: clear_minus.py <user_id> <domain>"}
            )
        )
        sys.exit(1)

    user_id = sys.argv[1]
    domain = sys.argv[2]

    result = clear_minus_words(user_id, domain)
    print(json.dumps(result, ensure_ascii=False))
