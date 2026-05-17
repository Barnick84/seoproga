# nodejs-app/scripts/run_mapping.py
import sys
import os
import json
from urllib.parse import urlparse

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
from services.clustering import merge_serps
from services.xmlriver_client import XmlriverClient
from services.cache import SERPCache
from services.task_manager import TaskManager

def normalize_domain(url):
    url = url.lower().strip()
    if url.startswith("http://"): url = url[7:]
    elif url.startswith("https://"): url = url[8:]
    domain = url.split('/')[0]
    if domain.startswith("www."): domain = domain[4:]
    return domain.rstrip("/")

def get_domain_from_url(url):
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path.split('/')[0]
    return normalize_domain(netloc)

def run_mapping():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: run_mapping.py <domain> <user_id> [cluster_id] [task_id]"}))
        return

    domain = normalize_domain(sys.argv[1])
    user_id = int(sys.argv[2])
    single_cluster_id = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != 'None' else None
    task_id = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    tm = TaskManager(task_id)
    tm.set_status('running')

    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # 1. Get cluster IDs
        if single_cluster_id:
            cur.execute(
                "SELECT DISTINCT clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
                (user_id, domain, single_cluster_id)
            )
        else:
            cur.execute(
                "SELECT DISTINCT clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered > 0",
                (user_id, domain)
            )
        cluster_ids = [r['clustered'] for r in cur.fetchall()]

        if not cluster_ids:
            tm.set_status('completed')
            print(json.dumps({"success": True, "message": "No clusters to map"}))
            return

        tm.update_progress(10)

        # 2. Network operations
        cache = SERPCache()
        client = XmlriverClient(cache=cache)
        mappings = {}
        total = len(cluster_ids)
        processed = 0

        for cid in cluster_ids:
            processed += 1
            tm.update_progress(10 + int((processed / total) * 80))
            
            cur.execute(
                "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
                (user_id, domain, cid)
            )
            keywords = [r['query'] for r in cur.fetchall()]
            
            if not keywords:
                mappings[cid] = None
                continue

            serps = [client.fetch_serp(k, use_cache=True) for k in keywords]
            serps = [s for s in serps if s]

            if not serps:
                mappings[cid] = None
                continue

            merged_urls = merge_serps(serps)

            best_url = None
            for url in merged_urls:
                if get_domain_from_url(url) == domain:
                    best_url = url
                    break

            if best_url:
                temp_url = best_url if best_url.startswith('http') else 'http://' + best_url
                parsed = urlparse(temp_url)
                rel_path = parsed.path
                if parsed.query:
                    rel_path += '?' + parsed.query
                mappings[cid] = rel_path
            else:
                mappings[cid] = None

        # 3. Save results
        for cid, target_url in mappings.items():
            cur.execute(
                "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE target_url = VALUES(target_url)",
                (user_id, domain, cid, target_url)
            )
        
        conn.commit()
        tm.set_status('completed')
        print(json.dumps({"success": True, "count": len(mappings)}))
        
    except Exception as e:
        tm.set_status('failed', str(e))
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    run_mapping()
