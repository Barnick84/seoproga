# nodejs-app/scripts/get_yandex_hosts.py
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

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "User ID required"}))
        return

    user_id = sys.argv[1]
    
    # 1. Get token from DB
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
            if host.get('verified', False):
                result.append({
                    "host_id": host['host_id'],
                    "unicode_host_url": host.get('unicode_host_url', host['host_id'])
                })
        
        print(json.dumps({"success": True, "hosts": result}))
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    main()
