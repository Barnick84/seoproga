from config import Config

def check():
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    tables = ['users', 'sites', 'yandex_queries', 'cluster_names', 'tasks', 'query_history']
    for t in tables:
        try:
            cur.execute(f'DESCRIBE {t}')
            print(f'\n--- {t} SCHEMA ---')
            for r in cur.fetchall():
                print(r)
            
            cur.execute(f'SELECT * FROM {t} LIMIT 5')
            print(f'--- {t} DATA (first 5) ---')
            for r in cur.fetchall():
                print(r)
        except Exception as e:
            print(f'\n--- {t} ERROR: {e} ---')
    conn.close()

if __name__ == "__main__":
    check()
