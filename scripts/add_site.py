# scripts/add_site.py
import sys
import os
import json
from datetime import datetime

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from utils.helpers import extract_domain


def add_site(domain, user_id):
    domain = extract_domain(domain)
    if not user_id:
        return {"success": False, "error": "user_id is required"}

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        # Check if exists for this user
        cur.execute(
            "SELECT id FROM sites WHERE domain = %s AND user_id = %s", (domain, user_id)
        )
        if cur.fetchone():
            return {"success": False, "error": "Сайт уже добавлен в ваш кабинет"}

        # Add site
        cur.execute(
            "INSERT INTO sites (domain, user_id) VALUES (%s, %s)",
            (domain, user_id),
        )
        site_id = cur.lastrowid
        return {"success": True, "id": site_id, "domain": domain}
    finally:
        conn.close()


if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else ""
    user_id = sys.argv[2] if len(sys.argv) > 2 else ""
    result = add_site(domain, user_id)
    print(json.dumps(result, ensure_ascii=False))
