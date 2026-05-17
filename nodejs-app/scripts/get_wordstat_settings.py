"""
get_wordstat_settings.py — CRUD операции для настроек Wordstat.
"""
import sys
import os
import json
import sqlite3

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)

DB_PATH = os.path.join(project_root, "data", "yandex_queries.db")


def ensure_settings_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wordstat_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device TEXT NOT NULL,
            region TEXT DEFAULT '',
            region_name TEXT DEFAULT 'Все регионы',
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Insert default preset if table is empty
    cur = conn.execute("SELECT COUNT(*) FROM wordstat_settings")
    if cur.fetchone()[0] == 0:
        conn.execute("""
            INSERT INTO wordstat_settings (name, device, region, region_name, is_default)
            VALUES ('Десктоп + Смартфоны, все регионы', 'desktop,phone', '', 'Все регионы', 1)
        """)
    conn.commit()


def get_settings():
    if not os.path.exists(DB_PATH):
        return {"settings": []}
    conn = sqlite3.connect(DB_PATH)
    ensure_settings_table(conn)
    cur = conn.execute("SELECT id, name, device, region, region_name, is_default FROM wordstat_settings ORDER BY is_default DESC, id ASC")
    rows = cur.fetchall()
    conn.close()
    settings = [
        {"id": r[0], "name": r[1], "device": r[2], "region": r[3], "region_name": r[4], "is_default": bool(r[5])}
        for r in rows
    ]
    return {"settings": settings}


def save_setting(name: str, device: str, region: str, region_name: str):
    conn = sqlite3.connect(DB_PATH)
    ensure_settings_table(conn)
    cur = conn.execute(
        "INSERT INTO wordstat_settings (name, device, region, region_name, is_default) VALUES (?, ?, ?, ?, 0)",
        (name, device, region, region_name)
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": new_id}


def delete_setting(setting_id: int):
    conn = sqlite3.connect(DB_PATH)
    ensure_settings_table(conn)
    # Don't delete default preset
    conn.execute("DELETE FROM wordstat_settings WHERE id = ? AND is_default = 0", (setting_id,))
    conn.commit()
    conn.close()
    return {"success": True}


def get_lsi_keywords(domain: str, cluster_id: int):
    if not os.path.exists(DB_PATH):
        return {"lsi": []}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "SELECT keyword, frequency FROM cluster_lsi WHERE site_url = ? AND cluster_id = ? ORDER BY frequency DESC",
            (domain, cluster_id)
        )
        rows = cur.fetchall()
        lsi = [{"keyword": r[0], "frequency": r[1]} for r in rows]
        return {"lsi": lsi}
    except Exception:
        return {"lsi": []}
    finally:
        conn.close()


def get_cluster_names(domain: str):
    if not os.path.exists(DB_PATH):
        return {"names": {}}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "SELECT cluster_id, cluster_name FROM cluster_names WHERE site_url = ?",
            (domain,)
        )
        rows = cur.fetchall()
        names = {str(r[0]): r[1] for r in rows}
        return {"names": names}
    except Exception:
        return {"names": {}}
    finally:
        conn.close()


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "get"

    if action == "get":
        print(json.dumps(get_settings(), ensure_ascii=False))
    elif action == "save":
        name = sys.argv[2] if len(sys.argv) > 2 else "Новый фильтр"
        device = sys.argv[3] if len(sys.argv) > 3 else "desktop"
        region = sys.argv[4] if len(sys.argv) > 4 else ""
        region_name = sys.argv[5] if len(sys.argv) > 5 else "Все регионы"
        print(json.dumps(save_setting(name, device, region, region_name), ensure_ascii=False))
    elif action == "delete":
        setting_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        print(json.dumps(delete_setting(setting_id), ensure_ascii=False))
    elif action == "lsi":
        domain = sys.argv[2] if len(sys.argv) > 2 else ""
        cluster_id = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        print(json.dumps(get_lsi_keywords(domain, cluster_id), ensure_ascii=False))
    elif action == "cluster_names":
        domain = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(get_cluster_names(domain), ensure_ascii=False))
    else:
        print(json.dumps({"error": f"Unknown action: {action}"}))
