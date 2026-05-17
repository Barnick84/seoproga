# scripts/copy_sqlite_to_mysql.py
import sqlite3
import pymysql
import os
import sys
import json
import bcrypt

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from config import Config

def copy_data():
    print("Starting data transfer from SQLite to MySQL...")
    
    try:
        # MySQL connection
        mysql_conn = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASS,
            database=Config.MYSQL_DB,
            charset='utf8mb4',
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )
        mysql_cur = mysql_conn.cursor()
        
        # 1. Ensure at least one user exists
        mysql_cur.execute("SELECT id FROM users LIMIT 1")
        user = mysql_cur.fetchone()
        if not user:
            print("No users found in MySQL. Creating 'admin' user...")
            hashed = bcrypt.hashpw("admin".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            mysql_cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", ("admin", hashed))
            user_id = mysql_conn.insert_id()
            print(f"User 'admin' created with ID: {user_id}")
        else:
            user_id = user['id']
            print(f"Using existing user ID: {user_id}")

        # 2. Migrate serp_cache (Shared)
        cache_db = os.path.join(project_root, "data", "serp_cache.db")
        if os.path.exists(cache_db):
            print("Migrating SERP cache...")
            with sqlite3.connect(cache_db) as sl_conn:
                sl_conn.row_factory = sqlite3.Row
                sl_cur = sl_conn.cursor()
                sl_cur.execute("SELECT * FROM serp_cache")
                rows = sl_cur.fetchall()
                for row in rows:
                    mysql_cur.execute(
                        "INSERT IGNORE INTO serp_cache (cache_key, urls, fetched_at) VALUES (%s, %s, %s)",
                        (row['cache_key'], row['urls'], row['fetched_at'])
                    )
            print(f"Migrated {len(rows)} SERP cache entries.")

        # 3. Migrate yandex_queries.db (User-specific)
        queries_db = os.path.join(project_root, "data", "yandex_queries.db")
        if os.path.exists(queries_db):
            with sqlite3.connect(queries_db) as sl_conn:
                sl_conn.row_factory = sqlite3.Row
                sl_cur = sl_conn.cursor()
                
                # Migrate yandex_queries
                print("Migrating Yandex queries...")
                sl_cur.execute("SELECT * FROM yandex_queries")
                rows = sl_cur.fetchall()
                sites = set()
                for sqlite_row in rows:
                    row = dict(sqlite_row)
                    sites.add(row['site_url'])
                    mysql_cur.execute(
                        "INSERT IGNORE INTO yandex_queries (user_id, site_url, query, period_from, period_to, hits, clicks, ctr, avg_position, fetched_at, minus_word, clustered, frequency) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (user_id, row['site_url'], row['query'], row.get('period_from'), row.get('period_to'), 
                         row.get('hits', 0), row.get('clicks', 0), row.get('ctr', 0), row.get('avg_position', 0), 
                         row.get('fetched_at'), row.get('minus_word', 0), row.get('clustered', 0), row.get('frequency', 0))
                    )
                print(f"Migrated {len(rows)} queries for {len(sites)} sites.")
                
                # Ensure sites are in the sites table
                for site in sites:
                    mysql_cur.execute("INSERT IGNORE INTO sites (domain, user_id) VALUES (%s, %s)", (site, user_id))

                # Migrate cluster_mappings
                print("Migrating cluster mappings...")
                try:
                    sl_cur.execute("SELECT * FROM cluster_mappings")
                    rows = sl_cur.fetchall()
                    for sqlite_row in rows:
                        row = dict(sqlite_row)
                        mysql_cur.execute(
                            "INSERT IGNORE INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (%s, %s, %s, %s)",
                            (user_id, row['site_url'], row['cluster_id'], row['target_url'])
                        )
                    print(f"Migrated {len(rows)} mappings.")
                except: pass

                # Migrate cluster_analysis
                print("Migrating cluster analysis...")
                try:
                    sl_cur.execute("SELECT * FROM cluster_analysis")
                    rows = sl_cur.fetchall()
                    for sqlite_row in rows:
                        row = dict(sqlite_row)
                        mysql_cur.execute(
                            "INSERT IGNORE INTO cluster_analysis (user_id, site_url, cluster_id, analysis_data, raw_html, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
                            (user_id, row['site_url'], row['cluster_id'], row['analysis_data'], row.get('raw_html'), row.get('updated_at'))
                        )
                    print(f"Migrated {len(rows)} analysis entries.")
                except: pass

                # Migrate wordstat_settings
                print("Migrating Wordstat settings...")
                try:
                    sl_cur.execute("SELECT * FROM wordstat_settings")
                    rows = sl_cur.fetchall()
                    for sqlite_row in rows:
                        row = dict(sqlite_row)
                        mysql_cur.execute(
                            "INSERT IGNORE INTO wordstat_settings (user_id, name, device, region, region_name, is_default) VALUES (%s, %s, %s, %s, %s, %s)",
                            (user_id, row['name'], row['device'], row['region'], row['region_name'], row.get('is_default', 0))
                        )
                    print(f"Migrated {len(rows)} settings presets.")
                except: pass

                # Migrate cluster_lsi
                print("Migrating cluster LSI...")
                try:
                    sl_cur.execute("SELECT * FROM cluster_lsi")
                    rows = sl_cur.fetchall()
                    for sqlite_row in rows:
                        row = dict(sqlite_row)
                        mysql_cur.execute(
                            "INSERT IGNORE INTO cluster_lsi (user_id, site_url, cluster_id, keyword, frequency) VALUES (%s, %s, %s, %s, %s)",
                            (user_id, row['site_url'], row['cluster_id'], row['keyword'], row.get('frequency', 0))
                        )
                    print(f"Migrated {len(rows)} LSI entries.")
                except: pass

                # Migrate cluster_names
                print("Migrating cluster names...")
                try:
                    sl_cur.execute("SELECT * FROM cluster_names")
                    rows = sl_cur.fetchall()
                    for sqlite_row in rows:
                        row = dict(sqlite_row)
                        mysql_cur.execute(
                            "INSERT IGNORE INTO cluster_names (user_id, site_url, cluster_id, cluster_name) VALUES (%s, %s, %s, %s)",
                            (user_id, row['site_url'], row['cluster_id'], row['cluster_name'])
                        )
                    print(f"Migrated {len(rows)} cluster names.")
                except: pass

        mysql_conn.close()
        print("Data transfer complete!")
        
    except Exception as e:
        print(f"Error during data transfer: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    copy_data()
