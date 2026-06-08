import sys
import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup
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

def clean_title(title: str) -> str:
    # Remove common site name separators and keep the main part
    parts = re.split(r'\s*[|\-:]\s*', title)
    return parts[0].strip() if parts else title.strip()

def fetch_wordstat_keywords(query: str) -> list[dict]:
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
            popular = data.get("table", {}).get("tableData", {}).get("popular", [])
            for item in popular:
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
    if len(sys.argv) < 4:
        safe_print(json.dumps({"success": False, "error": "Usage: script.py <domain> <user_id> <url>"}))
        sys.exit(1)

    domain = sys.argv[1].lower().strip()
    user_id = int(sys.argv[2])
    target_url = sys.argv[3].strip()

    try:
        # Fetch the target URL to extract title
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # Handle relative URLs if any
        full_url = target_url
        if not full_url.startswith('http'):
            full_url = f"https://{domain}{target_url if target_url.startswith('/') else '/' + target_url}"
            
        resp = requests.get(full_url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        title_tag = soup.find('title')
        if not title_tag or not title_tag.text:
            safe_print(json.dumps({"success": False, "error": "Не удалось найти тег <title> на странице"}))
            return
            
        raw_title = title_tag.text
        cleaned_title = clean_title(raw_title)
        
        if not cleaned_title:
            safe_print(json.dumps({"success": False, "error": "Пустой Title после очистки"}))
            return
            
        # Get candidates from Wordstat
        candidates = fetch_wordstat_keywords(cleaned_title)
        if not candidates:
            # Fallback to the title itself if Wordstat fails or gives nothing
            candidates = [{"query": cleaned_title, "freq": 0}]
        
        # Limit to top 30 to save requests/time
        candidates = sorted(candidates, key=lambda x: x["freq"], reverse=True)[:30]
        
        # Ensure the cleaned title itself is in the candidates
        if not any(c["query"].lower() == cleaned_title.lower() for c in candidates):
            candidates.insert(0, {"query": cleaned_title, "freq": 0})
            
        client = XmlriverClient()
        
        # Fetch SERP for the title (the baseline for our cluster)
        base_serp = client.fetch_serp(cleaned_title)
        if not base_serp:
            safe_print(json.dumps({"success": False, "error": "Не удалось получить SERP для Title страницы"}))
            return
            
        matched_keywords = []
        for cand in candidates:
            cand_serp = client.fetch_serp(cand["query"])
            sim = serp_similarity(base_serp, cand_serp)
            if sim >= Config.SIMILARITY_THRESHOLD or cand["query"].lower() == cleaned_title.lower():
                matched_keywords.append(cand)
                
        if not matched_keywords:
            safe_print(json.dumps({"success": False, "error": "Не найдено подходящих ключевых слов для кластера"}))
            return
            
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        try:
            # Check if cleaned_title exists in yandex_queries
            cur.execute(
                "SELECT id FROM yandex_queries WHERE user_id=%s AND site_url=%s AND query=%s",
                (user_id, domain, cleaned_title)
            )
            row = cur.fetchone()
            
            cluster_id = 0
            if row:
                cluster_id = row[0]
                cur.execute("UPDATE yandex_queries SET clustered=%s WHERE id=%s", (cluster_id, cluster_id))
            else:
                cur.execute(
                    "INSERT INTO yandex_queries (user_id, site_url, query, clustered, frequency, minus_word) "
                    "VALUES (%s, %s, %s, 0, 0, 0)",
                    (user_id, domain, cleaned_title)
                )
                cluster_id = cur.lastrowid
                cur.execute("UPDATE yandex_queries SET clustered=%s WHERE id=%s", (cluster_id, cluster_id))
                
            # Insert the rest of the matches
            added_count = 1
            for cand in matched_keywords:
                if cand["query"].lower() == cleaned_title.lower():
                    continue
                
                cur.execute(
                    "SELECT id FROM yandex_queries WHERE user_id=%s AND site_url=%s AND query=%s",
                    (user_id, domain, cand["query"])
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute("UPDATE yandex_queries SET clustered=%s, frequency=%s WHERE id=%s", (cluster_id, cand["freq"], existing[0]))
                else:
                    cur.execute(
                        "INSERT INTO yandex_queries (user_id, site_url, query, clustered, frequency, minus_word) "
                        "VALUES (%s, %s, %s, %s, %s, 0)",
                        (user_id, domain, cand["query"], cluster_id, cand["freq"])
                    )
                added_count += 1
                
            # Map the URL
            cur.execute(
                "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) "
                "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE target_url=%s",
                (user_id, domain, cluster_id, target_url, target_url)
            )
            
            conn.commit()
            
            safe_print(json.dumps({"success": True, "added": added_count, "cluster_id": cluster_id}))
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    except Exception as e:
        safe_print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    main()
