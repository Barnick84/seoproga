# nodejs-app/scripts/run_clustering.py
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
from services.clustering import cluster_keywords, merge_serps
from services.xmlriver_client import XmlriverClient
from services.cache import SERPCache
from services.task_manager import TaskManager

def normalize_domain(url):
    url = url.lower().strip()
    if url.startswith("http://"): url = url[7:]
    elif url.startswith("https://"): url = url[8:]
    return url.rstrip("/")

def run_clustering():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: run_clustering.py <domain> <user_id> [task_id]"}))
        return

    domain = normalize_domain(sys.argv[1])
    user_id = int(sys.argv[2])
    task_id = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    tm = TaskManager(task_id)
    tm.set_status('running')

    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # 1. Get existing clusters
        cur.execute(
            "SELECT query, clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND clustered > 0",
            (user_id, domain)
        )
        rows = cur.fetchall()
        
        cache = SERPCache()
        client = XmlriverClient(cache=cache)
        
        existing_groups = {}
        for row in rows:
            cid = row['clustered']
            kw = row['query']
            if cid not in existing_groups:
                existing_groups[cid] = []
            existing_groups[cid].append(kw)
            
        initial_clusters = []
        for cid, kws in existing_groups.items():
            serps = [client.fetch_serp(k, use_cache=True) for k in kws]
            serps = [s for s in serps if s]
            if serps:
                rep = merge_serps(serps)
                initial_clusters.append({
                    "id": cid,
                    "name": kws[0],
                    "keywords": kws,
                    "serp_representative": rep
                })

        # 2. Get unclustered keywords
        cur.execute(
            "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND clustered = 0",
            (user_id, domain)
        )
        unclustered_keywords = [r['query'] for r in cur.fetchall()]
        
        if not unclustered_keywords:
            tm.set_status('completed')
            print(json.dumps({"success": True, "message": "No new keywords to cluster"}))
            return

        tm.update_progress(10) # 10% progress

        # 3. Run incremental clustering
        # Note: cluster_keywords needs to be updated to handle progress if we want real-time updates inside it.
        all_clusters = cluster_keywords(unclustered_keywords, client, initial_clusters=initial_clusters)
        
        tm.update_progress(80) # 80% progress

        # 4. Update database with results
        for cluster in all_clusters:
            cluster_id = cluster["id"]
            for kw in cluster["keywords"]:
                cur.execute(
                    "UPDATE yandex_queries SET clustered = %s WHERE user_id = %s AND site_url = %s AND query = %s",
                    (cluster_id, user_id, domain, kw)
                )
        
        conn.commit()
        
        tm.set_status('completed')
        print(json.dumps({"success": True, "count": len(all_clusters)}))
        
    except Exception as e:
        tm.set_status('failed', str(e))
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(json.dumps({"success": False, "error": error_msg}))
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    run_clustering()
