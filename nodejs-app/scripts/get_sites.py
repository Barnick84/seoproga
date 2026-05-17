# scripts/get_sites.py
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


def get_all_sites(user_id):
    if not user_id:
        return {"sites": [], "count": 0}

    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT id, domain, created_at FROM sites WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        rows = cur.fetchall()
        sites = [
            {"id": r["id"], "domain": r["domain"], "created_at": str(r["created_at"])}
            for r in rows
        ]
        return {"sites": sites, "count": len(sites)}
    finally:
        conn.close()


if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else ""
    result = get_all_sites(user_id)
    print(json.dumps(result, ensure_ascii=False))
