# scripts/get_keywords.py
import sys
import os
import json
import argparse

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

def normalize_domain(url):
    url = url.lower().strip()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    url = url.rstrip("/")
    return url

def get_keywords(user_id, domain=None):
    if not user_id:
        return {"keywords": [], "count": 0, "domain": domain or "all", "minus_words": []}

    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        # Get minus words
        if domain:
            domain = normalize_domain(domain)
            cur.execute(
                "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 1",
                (user_id, domain),
            )
        else:
            cur.execute(
                "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND minus_word = 1",
                (user_id,),
            )
        minus_words = [r['query'] for r in cur.fetchall()]

        # Get keywords
        if domain:
            cur.execute(
                """SELECT q.id, q.query, q.hits, q.hits_ym, q.hits_google, q.minus_word, q.clustered, q.frequency, h.found_url 
                   FROM yandex_queries q
                   LEFT JOIN (
                       SELECT query, user_id, site_url, found_url 
                       FROM query_history 
                       WHERE id IN (SELECT MAX(id) FROM query_history GROUP BY query, user_id, site_url)
                   ) h ON q.query = h.query AND q.user_id = h.user_id AND q.site_url = h.site_url
                   WHERE q.user_id = %s AND q.site_url = %s 
                   ORDER BY q.hits DESC""",
                (user_id, domain),
            )
        else:
            cur.execute(
                """SELECT q.id, q.query, q.hits, q.hits_ym, q.hits_google, q.minus_word, q.clustered, q.frequency, h.found_url 
                   FROM yandex_queries q
                   LEFT JOIN (
                       SELECT query, user_id, site_url, found_url 
                       FROM query_history 
                       WHERE id IN (SELECT MAX(id) FROM query_history GROUP BY query, user_id, site_url)
                   ) h ON q.query = h.query AND q.user_id = h.user_id AND q.site_url = h.site_url
                   WHERE q.user_id = %s 
                   ORDER BY q.hits DESC""",
                (user_id,),
            )
        rows = cur.fetchall()

        keywords = [
            {
                "id": r['id'],
                "query": r['query'],
                "hits": r['hits'],
                "hits_ym": r['hits_ym'],
                "hits_google": r['hits_google'],
                "minus_word": r['minus_word'],
                "clustered": r['clustered'],
                "frequency": r['frequency'] or 0,
                "found_url": r['found_url']
            }
            for r in rows
        ]

        return {
            "keywords": keywords,
            "count": len(keywords),
            "domain": domain or "all",
            "minus_words": minus_words,
        }
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("user_id", help="ID of the user")
    parser.add_argument("domain", nargs="?", default=None, help="Domain to filter by")
    args = parser.parse_args()

    result = get_keywords(args.user_id, args.domain)
    print(json.dumps(result, ensure_ascii=False))
