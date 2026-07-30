from config import Config
conn = Config.get_conn()
cur = conn.cursor()
cur.execute("SELECT DISTINCT site_url FROM yandex_queries")
print("yandex_queries:", cur.fetchall())
cur.execute("SELECT DISTINCT domain FROM sites")
print("sites:", cur.fetchall())
