# nodejs-app/scripts/check_domain.py
import sys
import os
import json

# Fix console encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config
from services.yandex_webmaster import YandexWebmasterClient

def main(domain, user_id):
    try:
        token = None
        try:
            conn = Config.get_mysql_conn()
            cur = conn.cursor()
            cur.execute("SELECT yandex_token FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if row and row['yandex_token']:
                token = row['yandex_token']
            conn.close()
        except:
            pass

        if not token:
            token = Config.YANDEX_TOKEN

        if not token:
            print(json.dumps({"linked": False, "error": "No Yandex token found"}))
            return

        client = YandexWebmasterClient(token, user_id)
        y_user_id = client._get_user_id()
        host_id = client._get_host_id(domain, y_user_id)
        print(json.dumps({"linked": True, "host_id": host_id}))
    except Exception as e:
        print(json.dumps({"linked": False, "error": str(e)}))

if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else ""
    user_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    main(domain, user_id)
