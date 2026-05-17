Отличное решение! PostgreSQL надёжнее для продакшена, лучше работает с конкурентными запросами и имеет встроенные типы данных для векторов (`pgvector` пригодится на следующем этапе).

Ниже полный перевод модуля на **PostgreSQL**.

---

## 📝 Шаг 1: Обновляем `.env`

Добавьте параметры подключения к PostgreSQL:

```env
YANDEX_OAUTH_TOKEN=ваш_токен
YANDEX_SITE_URL=https://example.com

# PostgreSQL
PG_HOST=localhost
PG_PORT=5432
PG_DBNAME=seo_auto
PG_USER=postgres
PG_PASSWORD=your_secure_password
```

---

## 📦 Шаг 2: Обновляем `requirements.txt`

Замените/добавьте:

```txt
psycopg2-binary==2.9.9  # Драйвер PostgreSQL (бинарная сборка, не требует компиляции)
requests==2.31.0
xmltodict==0.13.0
python-dotenv==1.0.0
```

Выполните: `pip install -r requirements.txt`

---

## ⚙️ Шаг 3: Обновляем `config.py`

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Яндекс.Вебмастер
    YANDEX_TOKEN = os.getenv('YANDEX_OAUTH_TOKEN', '')
    YANDEX_SITE = os.getenv('YANDEX_SITE_URL', '')
    
    # PostgreSQL
    PG_HOST = os.getenv('PG_HOST', 'localhost')
    PG_PORT = int(os.getenv('PG_PORT', 5432))
    PG_DB = os.getenv('PG_DBNAME', 'seo_auto')
    PG_USER = os.getenv('PG_USER', 'postgres')
    PG_PASS = os.getenv('PG_PASSWORD', '')
    
    # Настройки кластеризации
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.4))
    SERP_TOP_N = 10
    CACHE_TTL_DAYS = 7
    
    # DSN для psycopg2
    @classmethod
    def get_pg_dsn(cls):
        return (
            f"host={cls.PG_HOST} port={cls.PG_PORT} "
            f"dbname={cls.PG_DB} user={cls.PG_USER} password={cls.PG_PASS}"
        )
        
    @classmethod
    def validate(cls):
        if not cls.YANDEX_TOKEN or not cls.YANDEX_SITE:
            raise ValueError("❌ Не заданы YANDEX_OAUTH_TOKEN или YANDEX_SITE_URL")
        if not cls.PG_PASS:
            raise ValueError("❌ Не задан PG_PASSWORD в .env")
        return True
```

---

## 🗄️ Шаг 4: Переписываем `services/yandex_webmaster.py` под PostgreSQL

```python
# services/yandex_webmaster.py
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import Config
import time

class YandexWebmasterClient:
    BASE_URL = "https://api.webmaster.yandex.net/v4"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json"
        })
        self.pg_dsn = Config.get_pg_dsn()
        self._init_db()

    def _init_db(self):
        """Создаёт таблицу и индексы, если их нет"""
        with psycopg2.connect(self.pg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS yandex_queries (
                        id SERIAL PRIMARY KEY,
                        site_url TEXT NOT NULL,
                        query TEXT NOT NULL,
                        period_from DATE NOT NULL,
                        period_to DATE NOT NULL,
                        hits INTEGER DEFAULT 0,
                        clicks INTEGER DEFAULT 0,
                        ctr DOUBLE PRECISION DEFAULT 0.0,
                        avg_position DOUBLE PRECISION DEFAULT 0.0,
                        fetched_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(site_url, query, period_from, period_to)
                    );
                """)
                # Индексы для ускорения выборок
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_yq_site_hits 
                    ON yandex_queries(site_url, hits) WHERE hits > 0;
                    CREATE INDEX IF NOT EXISTS idx_yq_period 
                    ON yandex_queries(period_from, period_to);
                """)
                conn.commit()

    def _get_user_id(self) -> str:
        resp = self.session.get(f"{self.BASE_URL}/user")
        resp.raise_for_status()
        return resp.json()["uid"]

    def _get_host_id(self, site_url: str, user_id: str) -> str:
        resp = self.session.get(f"{self.BASE_URL}/user/{user_id}/hosts")
        resp.raise_for_status()
        hosts = resp.json().get("hosts", [])
        target = site_url.lower().strip("/")
        for host in hosts:
            if target in host["host_id"].lower().strip("/"):
                return host["host_id"]
        raise ValueError(f"❌ Сайт {site_url} не найден в Вебмастере")

    def fetch_queries_last_7_days(self, site_url: str) -> List[Dict]:
        user_id = self._get_user_id()
        host_id = self._get_host_id(site_url, user_id)

        # Данные в Вебмастере обновляются с задержкой ~2 дня
        end_date = datetime.now() - timedelta(days=2)
        start_date = end_date - timedelta(days=7)

        params = {
            "query_date_from": start_date.strftime("%Y-%m-%d"),
            "query_date_to": end_date.strftime("%Y-%m-%d"),
            "device_type": "ALL",
            "page_size": 100,
            "page": 0
        }

        all_queries = []
        page = 0

        print(f"📡 Загружаю запросы: {params['query_date_from']} → {params['query_date_to']}")

        while True:
            params["page"] = page
            resp = self.session.get(
                f"{self.BASE_URL}/user/{user_id}/hosts/{host_id}/query-list",
                params=params
            )
            resp.raise_for_status()
            data = resp.json()

            queries = data.get("queries", [])
            all_queries.extend(queries)
            total_pages = data.get("total_pages", 1)
            print(f"   📄 Страница {page + 1}/{total_pages} | Запросов: {len(queries)}")

            if page >= total_pages - 1:
                break
            page += 1
            time.sleep(0.5)

        # Обогащаем метаданными
        for q in all_queries:
            q["site_url"] = site_url
            q["period_from"] = params["query_date_from"]
            q["period_to"] = params["query_date_to"]

        return all_queries

    def save_queries_to_db(self, queries: List[Dict]) -> int:
        """UPSERT в PostgreSQL (ON CONFLICT DO UPDATE)"""
        if not queries:
            return 0

        sql = """
            INSERT INTO yandex_queries 
            (site_url, query, period_from, period_to, hits, clicks, ctr, avg_position)
            VALUES %s
            ON CONFLICT (site_url, query, period_from, period_to) DO UPDATE SET
                hits = EXCLUDED.hits,
                clicks = EXCLUDED.clicks,
                ctr = EXCLUDED.ctr,
                avg_position = EXCLUDED.avg_position,
                fetched_at = NOW();
        """

        # Подготавливаем данные для execute_values
        values = [
            (q["site_url"], q["query"], q["period_from"], q["period_to"],
             q.get("hits", 0), q.get("clicks", 0), q.get("ctr", 0.0), q.get("avg_position", 0.0))
            for q in queries
        ]

        with psycopg2.connect(self.pg_dsn) as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, values, page_size=500)
                conn.commit()
                
        return len(values)

    def get_unique_queries_for_clustering(self, site_url: str, min_hits: int = 5) -> List[str]:
        """Возвращает уникальные запросы с показов >= min_hits"""
        with psycopg2.connect(self.pg_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT query FROM yandex_queries WHERE site_url = %s AND hits >= %s ORDER BY query",
                    (site_url, min_hits)
                )
                return [row[0] for row in cur.fetchall()]
```

---

## 🔗 Шаг 5: Обновляем `main.py`

```python
# main.py
import os
from config import Config
from services.yandex_webmaster import YandexWebmasterClient

def main():
    try:
        Config.validate()
    except ValueError as e:
        print(e)
        return

    print("🚀 Запуск модуля Яндекс.Вебмастер + PostgreSQL...")
    
    client = YandexWebmasterClient(Config.YANDEX_TOKEN)
    
    try:
        # 1. Загрузка
        raw_queries = client.fetch_queries_last_7_days(Config.YANDEX_SITE)
        if not raw_queries:
            print("⚠️ Запросы не найдены. Проверьте, что сайт добавлен в Вебмастер и прошло >2 дней с индексации.")
            return

        # 2. Сохранение в PG
        saved = client.save_queries_to_db(raw_queries)
        print(f"✅ Сохранено/обновлено в PostgreSQL: {saved} записей")

        # 3. Подготовка к кластеризации
        keywords = client.get_unique_queries_for_clustering(Config.YANDEX_SITE, min_hits=5)
        print(f"🔑 Уникальных запросов для кластеризации (hits ≥ 5): {len(keywords)}")
        if keywords:
            print("   Примеры:", keywords[:5])

    except requests.exceptions.HTTPError as e:
        print(f"❌ Ошибка API: {e.response.status_code} → {e.response.text}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()
```

---

## 🐘 PostgreSQL: важные нюансы для продакшена

| Аспект | Рекомендация |
|--------|--------------|
| **Подключение** | Для >50 одновременных подключений используйте пуллер (`pgbouncer` или `SQLAlchemy` + `QueuePool`) |
| **Массовая вставка** | `execute_values` уже встроена в код выше → в 10-50 раз быстрее `executemany` |
| **Конфликты** | `ON CONFLICT (...) DO UPDATE SET ...` работает только если в таблице есть `UNIQUE` constraint по этим полям (в коде уже добавлен) |
| **Типы данных** | `DOUBLE PRECISION` для `ctr`/`avg_position` → точность до 15 знаков, достаточно для SEO-метрик |
| **Бэкапы** | `pg_dump -U postgres -d seo_auto > backup.sql` |

---

## ✅ Проверка работы

1. Убедитесь, что PostgreSQL запущен и база `seo_auto` создана:

```bash
# В терминале
createdb -U postgres seo_auto
```

1. Запустите скрипт:

```bash
python main.py
```

1. Проверьте данные в БД:

```sql
\c seo_auto
SELECT COUNT(*), SUM(hits) FROM yandex_queries;
SELECT query, hits, avg_position FROM yandex_queries ORDER BY hits DESC LIMIT 5;
```

---

## 🔄 Что дальше?

Теперь у вас:
✅ Данные из Вебмастера автоматически загружаются  
✅ Хранятся в PostgreSQL с защитой от дублей  
✅ Готовы к передаче в `cluster_keywords()` (из предыдущих шагов)

Нужен модуль, который **забирает эти ключи из PG → кластеризует → сохраняет кластеры обратно в новые таблицы** (`clusters`, `cluster_keywords`, `cluster_page_mapping`)? Напишу за 5 минут. 🚀
