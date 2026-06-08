import sys
import os
import json
import requests
from collections import defaultdict

# Fix console encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    except Exception:
        pass

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config
from services.xmlriver_client import XmlriverClient
from services.clustering import serp_similarity

def fetch_wordstat_keywords(query: str, type_name: str = "popular") -> list[dict]:
    url = "https://xmlriver.com/wordstat/new/json"
    params = {
        "query": query,
        "key": Config.XMLRIVER_KEY,
        "user": Config.XMLRIVER_USER,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        candidates = []
        try:
            items = data.get("table", {}).get("tableData", {}).get(type_name, [])
            for item in items:
                text = item.get("text", "").strip()
                val = int(item.get("value", 0))
                if text:
                    candidates.append({"query": text, "freq": val})
        except Exception:
            pass
            
        return candidates
    except Exception as e:
        print(f"WARN: Wordstat fetch error: {e}", file=sys.stderr)
        return []

def main():
    if len(sys.argv) < 5:
        safe_print(json.dumps({"success": False, "error": "Usage: script.py <domain> <user_id> <cluster_id> <head_query> [type]"}))
        sys.exit(1)

    domain = sys.argv[1].lower().strip()
    user_id = int(sys.argv[2])
    cluster_id = int(sys.argv[3])
    head_query = sys.argv[4].strip()
    source_type = sys.argv[5].strip().lower() if len(sys.argv) > 5 else "popular"
    if source_type not in ["popular", "similar"]:
        source_type = "popular"

    try:
        # Get candidates from Wordstat
        candidates = fetch_wordstat_keywords(head_query, source_type)
        if not candidates:
            safe_print(json.dumps({"success": True, "added": 0, "message": f"В Яндекс Wordstat нет запросов в колонке '{source_type}' по этому ключу"}))
            return
        
        # Limit to top 30 to save requests/time
        candidates = sorted(candidates, key=lambda x: x["freq"], reverse=True)[:30]
        
        client = XmlriverClient()
        
        # Fetch SERP for the head query (the baseline for our cluster)
        base_serp = client.fetch_serp(head_query)
        if not base_serp:
            safe_print(json.dumps({"success": False, "error": "Не удалось получить SERP для главного запроса кластера"}))
            return
            
        matched_keywords = []
        for cand in candidates:
            if cand["query"].lower() == head_query.lower():
                continue
            cand_serp = client.fetch_serp(cand["query"])
            sim = serp_similarity(base_serp, cand_serp)
            if sim >= Config.SIMILARITY_THRESHOLD:
                matched_keywords.append(cand)
                
        if not matched_keywords:
            safe_print(json.dumps({"success": True, "added": 0, "message": "Подходящих ключевых слов по близости SERP не найдено"}))
            return
            
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        is_rc = 1 if source_type == "similar" else 0
        try:
            added_count = 0
            for cand in matched_keywords:
                cur.execute(
                    "SELECT id FROM yandex_queries WHERE user_id=%s AND site_url=%s AND query=%s",
                    (user_id, domain, cand["query"])
                )
                existing = cur.fetchone()
                if existing:
                    # Update cluster mapping and frequency if already exists, and preserve/update right column flag
                    cur.execute("UPDATE yandex_queries SET clustered=%s, frequency=%s, is_right_column=%s WHERE id=%s", (cluster_id, cand["freq"], is_rc, existing[0]))
                else:
                    # Insert new keyword
                    cur.execute(
                        "INSERT INTO yandex_queries (user_id, site_url, query, clustered, frequency, minus_word, is_right_column) "
                        "VALUES (%s, %s, %s, %s, %s, 0, %s)",
                        (user_id, domain, cand["query"], cluster_id, cand["freq"], is_rc)
                    )
                added_count += 1
                
            conn.commit()
            
            safe_print(json.dumps({"success": True, "added": added_count}))
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    except Exception as e:
        safe_print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    main()
