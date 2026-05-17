# nodejs-app/scripts/run_competitor_analysis.py
import sys
import os
import json
import requests
from datetime import datetime

# Fix console encoding on Windows
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config
from services.custom_analyzer import CustomAnalyzer
from services.task_manager import TaskManager

def run_analysis():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: run_competitor_analysis.py <domain> <user_id> ..."}))
        return

    domain = sys.argv[1].lower().strip()
    if domain.startswith("xn--"):
        try:
            domain = domain.encode("ascii").decode("idna")
        except Exception:
            pass

    user_id = int(sys.argv[2])
    target_cluster_id = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != 'None' else None
    task_id = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    tm = TaskManager(task_id)
    tm.set_status('running')

    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # 1. Get mappings
        if target_cluster_id:
            cur.execute(
                "SELECT cluster_id, target_url FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (user_id, domain, target_cluster_id)
            )
        else:
            cur.execute(
                "SELECT cluster_id, target_url FROM cluster_mappings WHERE user_id = %s AND site_url = %s",
                (user_id, domain)
            )
        mappings = cur.fetchall()
        
        if not mappings:
            tm.set_status('completed', "No mappings found")
            print(json.dumps({"success": True, "message": "No mappings found"}))
            return

        analyzer = CustomAnalyzer()
        results_count = 0
        total = len(mappings)
        
        for idx, row in enumerate(mappings):
            cid = row['cluster_id']
            target_url = row['target_url']
            
            tm.update_progress(int((idx / total) * 100))
            
            # Get keywords
            cur.execute(
                "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
                (user_id, domain, cid)
            )
            keywords = [r['query'] for r in cur.fetchall()]
            
            if not keywords or not target_url:
                continue

            try:
                # URL normalization
                full_target_url = target_url
                if not target_url.startswith('http'):
                    base = domain if domain.startswith('http') else 'https://' + domain
                    full_target_url = base.rstrip('/') + '/' + target_url.lstrip('/')

                # Fetch and analyze with Punycode URL normalization and Chrome User-Agent
                from urllib.parse import urlparse
                fetch_url = full_target_url
                try:
                    parsed = urlparse(full_target_url)
                    if parsed.netloc:
                        puny_netloc = parsed.netloc.encode('idna').decode('ascii')
                        fetch_url = full_target_url.replace(parsed.netloc, puny_netloc)
                except Exception:
                    pass

                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                resp = requests.get(fetch_url, timeout=20, headers=headers)
                resp.raise_for_status()
                raw_html = resp.text

                analysis = analyzer.process_analysis(full_target_url, keywords, raw_html=raw_html)
                
                # Save to DB
                cur.execute(
                    "INSERT INTO cluster_analysis (user_id, site_url, cluster_id, analysis_data, raw_html) "
                    "VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE analysis_data = VALUES(analysis_data), raw_html = VALUES(raw_html)",
                    (user_id, domain, cid, json.dumps(analysis, ensure_ascii=False), raw_html)
                )
                results_count += 1
                conn.commit()
            except Exception as e:
                print(f"Error analyzing cluster {cid}: {e}", file=sys.stderr)
                continue

        tm.set_status('completed')
        print(json.dumps({"success": True, "count": results_count}))
        
    except Exception as e:
        tm.set_status('failed', str(e))
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    run_analysis()
