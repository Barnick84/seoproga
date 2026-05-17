# scripts/add_site.py
import sys
import os
import json
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

def normalize_domain(url):
    url = url.lower().strip()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    url = url.rstrip("/")
    return url

def add_site(domain, user_id):
    domain = normalize_domain(domain)
    if not user_id:
        return {"success": False, "error": "user_id is required"}

    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        # Check if exists for this user
        cur.execute("SELECT id FROM sites WHERE domain = %s AND user_id = %s", (domain, user_id))
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
