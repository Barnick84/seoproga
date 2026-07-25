# nodejs-app/scripts/get_yandex_hosts.py
import json
import os
import sys

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.yandex_webmaster import YandexWebmasterClient


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "User ID required"}))
        return

    user_id = sys.argv[1]

    # 1. Get token from DB
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
        print(json.dumps({"success": False, "error": "Yandex token not found"}))
        return

    try:
        client = YandexWebmasterClient(token, user_id)
        hosts = client.list_hosts()

        # Filter verified hosts only if needed, or return all
        result = []
        for host in hosts:
            if host.get("verified", False):
                result.append(
                    {
                        "host_id": host["host_id"],
                        "unicode_host_url": host.get("unicode_host_url", host["host_id"]),
                    }
                )

        print(json.dumps({"success": True, "hosts": result}))

    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))


if __name__ == "__main__":
    main()
