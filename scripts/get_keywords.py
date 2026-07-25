# scripts/get_keywords.py
import argparse
import json

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from utils.helpers import extract_domain


def get_keywords(user_id, domain=None):
    if not user_id:
        return {
            "keywords": [],
            "count": 0,
            "domain": domain or "all",
            "minus_words": [],
        }

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        # Get minus words
        if domain:
            domain = extract_domain(domain)
            cur.execute(
                "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 1",
                (user_id, domain),
            )
        else:
            cur.execute(
                "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND minus_word = 1",
                (user_id,),
            )
        minus_words = [r["query"] for r in cur.fetchall()]

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
                "id": r["id"],
                "query": r["query"],
                "hits": r["hits"],
                "hits_ym": r["hits_ym"],
                "hits_google": r["hits_google"],
                "minus_word": r["minus_word"],
                "clustered": r["clustered"],
                "frequency": r["frequency"] or 0,
                "found_url": r["found_url"],
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
