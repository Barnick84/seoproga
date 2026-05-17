import sys
import os
import pymysql

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from config import Config

def main():
    conn = Config.get_mysql_conn()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    
    cur.execute(
        "SELECT query, clustered, minus_word FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
        (1, "русский-кавказ.рф", 270)
    )
    rows = cur.fetchall()
    print(f"Keywords count for cluster 270: {len(rows)}")
    for r in rows:
        print(f" - Query: {r.get('query')}, Clustered: {r.get('clustered')}, Minus: {r.get('minus_word')}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
