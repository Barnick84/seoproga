# nodejs-app/scripts/scheduler.py
import sys
import os
import json
import time
from datetime import datetime

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

def run_daily_update():
    print(f"[{datetime.now()}] 🔄 Starting daily background update...")
    
    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # 1. Get all active users with tokens
        cur.execute("SELECT id, username, yandex_token FROM users WHERE is_blocked = 0 AND yandex_token IS NOT NULL")
        users = cur.fetchall()
        
        total_sites = 0
        total_queries = 0
        
        for user in users:
            user_id = user['id']
            token = user['yandex_token']
            if not token:
                token = os.getenv("YANDEX_OAUTH_TOKEN")
            
            if not token:
                print(f"  ⚠️ Skipping user {user['username']}: No token")
                continue
                
            username = user['username']
            
            # 2. Get sites for this user
            cur.execute("SELECT domain FROM sites WHERE user_id = %s", (user_id,))
            sites = cur.fetchall()
            
            if not sites:
                continue
                
            print(f"👤 User: {username} ({len(sites)} sites)")
            client = YandexWebmasterClient(token, user_id)
            
            for site in sites:
                domain = site['domain']
                print(f"  🌐 Processing: {domain}...")
                
                try:
                    queries = client.fetch_queries_recent(domain)
                    if queries:
                        saved = client.save_queries_to_db(queries)
                        print(f"    ✅ Saved {saved} queries")
                        total_queries += saved
                    else:
                        print(f"    ℹ️ No new queries found")
                    
                    total_sites += 1
                except Exception as e:
                    print(f"    ❌ Error for {domain}: {e}")
                
                time.sleep(1) # Avoid rate limits
                
        conn.close()
        print(f"[{datetime.now()}] ✅ Update finished. Sites: {total_sites}, Queries: {total_queries}")
        
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Global scheduler error: {e}")

if __name__ == "__main__":
    run_daily_update()
