from config import Config

def fix():
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    
    commands = [
        "ALTER TABLE yandex_queries ADD COLUMN hits_ym INT DEFAULT 0 AFTER hits",
        "ALTER TABLE yandex_queries ADD COLUMN hits_google INT DEFAULT 0 AFTER hits_ym",
        "ALTER TABLE yandex_queries ADD COLUMN last_check TIMESTAMP NULL AFTER frequency",
        "ALTER TABLE cluster_names ADD COLUMN is_favorite TINYINT DEFAULT 0 AFTER cluster_name",
        "ALTER TABLE cluster_names ADD COLUMN is_pinned TINYINT DEFAULT 0 AFTER is_favorite",
        "ALTER TABLE cluster_names ADD COLUMN pinned_order INT DEFAULT 0 AFTER is_pinned"
    ]
    
    for cmd in commands:
        try:
            cur.execute(cmd)
            print(f"Executed: {cmd}")
        except Exception as e:
            # MariaDB/MySQL might not support ADD COLUMN IF NOT EXISTS in all versions
            # So we catch the "column already exists" error
            if "Duplicate column name" in str(e):
                print(f"Skipped (already exists): {cmd}")
            else:
                print(f"Error executing {cmd}: {e}")
    
    conn.commit()
    conn.close()
    print("Database fix completed.")

if __name__ == "__main__":
    fix()
