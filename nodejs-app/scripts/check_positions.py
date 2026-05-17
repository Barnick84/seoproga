# nodejs-app/scripts/check_positions.py
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
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain

def check_target(client, query, engine, device, region, clean_target_domain):
    found_pos = 0
    found_url = ""
    
    # Fetch SERP page by page (up to 10 pages)
    for page in range(10):
        try:
            serp_urls = client.fetch_serp(query, engine=engine, device=device, region=region, top_n=10, page=page, use_cache=False)
            if not serp_urls:
                break
            
            page_pos = 0
            for url in serp_urls:
                page_pos += 1
                if clean_target_domain in extract_domain(url):
                    found_pos = (page * 10) + page_pos
                    found_url = url
                    break
            
            if found_pos > 0:
                break
                
            time.sleep(1)
        except Exception as e:
            print(f"Error checking {engine}/{device}: {e}", file=sys.stderr)
            break
            
    return found_pos, found_url

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: check_positions.py <domain> <cluster_id> [user_id]"}))
        return
        
    domain = sys.argv[1].lower().strip()
    clean_target_domain = extract_domain(domain)
    cluster_id = int(sys.argv[2])
    user_id = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cmd_region = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None

    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    
    try:
        # 0. Get user region
        if cmd_region and cmd_region.isdigit():
            user_region = int(cmd_region)
        else:
            cur.execute("SELECT yandex_region_id FROM user_settings WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            user_region = row['yandex_region_id'] if row else 213

        # 1. Get keywords
        cur.execute(
            "SELECT id, query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
            (user_id, domain, cluster_id)
        )
        keywords = cur.fetchall()
        
        if not keywords:
            print(json.dumps({"success": True, "message": "No keywords in cluster", "positions": []}))
            return

        client = XmlriverClient()
        results = []
        
        for kw in keywords:
            query = kw['query']
            kw_id = kw['id']
            
            print(f"PROGRESS: Checking {query}...")
            sys.stdout.flush()
            
            # Check Yandex Desktop
            print(f"PROGRESS: > Yandex Desktop...")
            sys.stdout.flush()
            pos_yd, url_yd = check_target(client, query, "yandex", "desktop", user_region, clean_target_domain)
            
            # Check Yandex Mobile
            print(f"PROGRESS: > Yandex Mobile...")
            sys.stdout.flush()
            pos_ym, url_ym = check_target(client, query, "yandex", "mobile", user_region, clean_target_domain)
            
            # Check Google Desktop (Region Russia = 225)
            print(f"PROGRESS: > Google Desktop...")
            sys.stdout.flush()
            pos_g, url_g = check_target(client, query, "google", "desktop", 225, clean_target_domain)
            
            results.append({
                "query": query,
                "pos_yd": pos_yd,
                "pos_ym": pos_ym,
                "pos_g": pos_g,
                "url_yd": url_yd,
                "url_ym": url_ym,
                "url_g": url_g
            })
            
            # Save to history
            targets = [
                ("yandex", "desktop", pos_yd, url_yd, user_region),
                ("yandex", "mobile", pos_ym, url_ym, user_region),
                ("google", "desktop", pos_g, url_g, 225)
            ]
            for engine, device, pos, url, reg in targets:
                cur.execute(
                    """INSERT INTO query_history (user_id, site_url, query, position, found_url, engine, device, region_id) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, domain, query, pos, url, engine, device, reg)
                )
            
            # Update main query table
            cur.execute(
                """UPDATE yandex_queries 
                   SET hits = %s, hits_ym = %s, hits_google = %s, last_check = %s 
                   WHERE id = %s""",
                (pos_yd, pos_ym, pos_g, datetime.now(), kw_id)
            )
            
            time.sleep(0.5)

        conn.commit()
        print(json.dumps({
            "success": True,
            "message": f"Checked {len(results)} keywords on 3 engines",
            "positions": results
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
