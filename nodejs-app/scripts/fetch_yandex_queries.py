# nodejs-app/scripts/fetch_yandex_queries.py
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
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: fetch_yandex_queries.py <domain> <user_id>"}))
        return

    domain = sys.argv[1]
    user_id = int(sys.argv[2])
    
    # Try to get token from DB
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
        
        # 1. Fetch recent queries
        queries = client.fetch_queries_recent(domain)
        
        if not queries:
            print(json.dumps({"success": True, "message": "No queries found", "added": 0}))
            return

        # 2. Save to DB
        added = client.save_queries_to_db(queries)
        
        print(json.dumps({
            "success": True, 
            "message": f"Successfully fetched {len(queries)} queries", 
            "added": added
        }))
        
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(json.dumps({"success": False, "error": error_msg}))

if __name__ == "__main__":
    main()
