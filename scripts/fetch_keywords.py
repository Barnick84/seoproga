# scripts/fetch_keywords.py
import json
import sys

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.yandex_webmaster import YandexWebmasterClient


def main(domain, user_id: int):
    if not Config.YANDEX_TOKEN:
        print(json.dumps({"count": 0, "error": "No token"}))
        return

    try:
        client = YandexWebmasterClient(Config.YANDEX_TOKEN, user_id=user_id)

        queries = client.fetch_queries_recent(domain)

        if queries:
            saved = client.save_queries_to_db(queries)
        else:
            saved = 0

        keywords = [
            {
                "query": q.get("query_text", q.get("query", "")),
                "hits": q.get("shows", q.get("hits", 0)),
            }
            for q in queries
        ]

        print(json.dumps({"count": saved, "keywords": keywords}))
    except Exception as e:
        print(json.dumps({"count": 0, "error": str(e)}))


if __name__ == "__main__":
    domain_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    user_id_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    main(domain_arg, user_id_arg)
