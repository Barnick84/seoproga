# Архитектура и Описание Проекта seo-auto-cluster

## 1. Обзор проекта

**seo-auto-cluster** — платформа для автоматизации SEO-процессов, ориентированная на русскоязычный рынок. Это полностью Python-инфраструктура, объединяющая веб-интерфейс на базе FastAPI (со встроенной раздачей статики) и мощный аналитический бэкенд с асинхронными очередями задач.

**Основные функции:**
- Сбор семантического ядра (ключевых слов) из Яндекс.Вебмастера
- Кластеризация ключей по схожести поисковой выдачи (SERP) через XMLRiver
- Маппинг кластеров на страницы сайта
- SEO-анализ и генерация контента через LLM (OpenAI/Hydra) и Miratext
- Биллинговая система (списание средств за операции, пополнение через Cardlink)
- Фоновый воркер для длительных задач (частотность, кластеризация, конкурентный анализ)

---

## 2. Архитектура и Data Flow

```
┌──────────────────────────────────────────────────────────┐
│                   Browser (Frontend)                      │
│  index.html | cluster.html | sort.html | analysis.html   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / SSE / Polling
                           ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI Server (api/main.py)                 │
│  ├── Аутентификация (JWT + HttpOnly Cookies, bcrypt)     │
│  ├── REST API (JSON) + SSE (Server-Sent Events)          │
│  ├── Раздача статических файлов (api/public)             │
│  └── Управление задачами (INSERT в таблицу tasks)        │
└─────────────┬──────────────────────────┬─────────────────┘
              │                          │
              ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  Python Backend (CLI)     │  │  MySQL Database           │
│  main.py (4 режима)      │  │  ├── users                │
│  services/ (ядро)        │  │  ├── yandex_queries      │
│  scripts/ (фоновые)      │  │  ├── cluster_mappings    │
│  worker.py (очередь)     │  │  ├── tasks               │
└──────────────────────────┘  │  ├── serp_cache          │
                              │  └── ...                 │
                              └───────▲──────────────────┘
                                      │
                                      │ Connection Pooling (DBUtils.PooledDB)
```

**Основные потоки данных:**

```
1. Yandex WM → yandex_queries (MySQL) → cluster_keywords() → clusters
2. clusters → cluster_mappings (MySQL) → страницы сайта
3. cluster → SEO analysis → cluster_analysis (MySQL, JSON)
4. cluster → generate_seo_plan → cluster_seo_history (MySQL)
5. Miratext → MiratextClient → SEOAgent (LLM) → rewritten HTML
6. FastAPI → MySQL tasks → worker.py (daemon) → spawn scripts → TaskManager.update_progress()
```

---

## 3. Полная структура файлов

```
seo-auto-cluster/
│
├── main.py                     # CLI точка входа (4 режима)
├── config.py                   # Конфигурация из .env
├── streamlit_app.py            # Streamlit дашборд (альтернативный UI)
├── ARCH.md                     # Этот файл
├── AGENTS.md                   # Инструкции для AI-агента
├── requirements.txt            # Python зависимости
├── docker-compose.yml          # MySQL 8.0 для прода
├── .env                        # Секреты (токены, пароли) — в .gitignore
├── yandex_geo.csv              # CSV-справочник регионов Яндекса
│
├── services/                   # Python-ядро (бизнес-логика)
│   ├── auth.py                 # Логика аутентификации (bcrypt + legacy pbkdf2)
│   ├── cache.py                # MySQL-кэш SERP (TTL 7 дней), lazy connection
│   ├── clustering.py           # Алгоритм кластеризации (Jaccard + позиции), инкрементальный merge
│   ├── custom_analyzer.py      # Глубокий SEO-анализ контента (асинхронный через aiohttp)
│   ├── miratext_client.py      # Клиент Miratext API
│   ├── page_content_manager.py # Управление контентом страниц (PostgreSQL)
│   ├── semantic_core.py        # Хранение сем. ядра (PostgreSQL)
│   ├── seo_agent.py            # LLM-агент (OpenAI/Hydra)
│   ├── seo_workflow.py         # Оркестратор полного SEO-цикла
│   ├── task_manager.py         # Менеджер прогресса задач (MySQL)
│   ├── worker.py               # Фоновый воркер задач (с поддержкой threading.Lock)
│   ├── serp_collector.py       # Prefetch SERP с прогрессом
│   ├── xmlriver_client.py      # Клиент XMLRiver API (rate limiting 1.5с)
│   └── yandex_webmaster.py     # Клиент Яндекс.Вебмастер API v4
│
├── utils/
│   ├── bootstrap.py             # Единая точка входа скриптов (chdir, sys.path, stdout)
│   ├── retry.py                 # Декоратор with_retry (exponential backoff)
│   └── helpers.py               # Утилиты: extract_domain, clean_url, safe_divide
│
├── api/                        # FastAPI веб-сервер
│   ├── main.py                 # Главная точка входа (uvicorn api.main:app)
│   ├── dependencies.py         # Зависимости FastAPI (аутентификация, БД)
│   ├── routers/                # Маршруты API
│   │   ├── health.py           # /health, /ready
│   │   ├── users.py            # Регистрация, логин, профиль, настройки
│   │   ├── sites.py            # Добавление/проверка сайтов
│   │   ├── keywords.py         # Ключевые слова, минус-слова
│   │   ├── analysis.py         # Кластеризация, маппинг, частотность (запуск фоновых задач)
│   │   ├── billing.py          # Cardlink платежи и вебхуки
│   │   ├── admin.py            # Админ-панель (тарифы, пользователи, логи)
│   │   ├── cluster.py          # Кластеры: маппинг, LSI, SEO-история
│   │   ├── structure.py        # Структура сайта: ИИ генерация карты, редактирование дерева, типы страниц
│   │   ├── wordstat.py         # Настройки Wordstat, регионы
│   │   └── positions.py        # Мониторинг позиций
│   │
│   └── public/                 # Статические HTML-страницы (раздаются сервером Nginx/FastAPI)
│       ├── index.html          # Дашборд сайтов
│       ├── cluster.html        # Управление кластерами
│       ├── sort.html           # Сортировка и минус-слова
│       ├── structure.html      # Структура сайта (интерактивное дерево, ИИ генератор, типы страниц)
│       ├── analysis.html       # SEO анализ кластера
│       ├── positions.html      # Мониторинг позиций
│       ├── cabinet.html        # Личный кабинет
│       ├── admin.html          # Админ-панель
│       ├── style.css           # Основные стили
│       └── app.js              # Основная фронтенд логика
│
├── scripts/                    # Python-скрипты для фоновых задач
│   ├── run_clustering.py       # Запуск кластеризации
│   ├── run_mapping.py          # Маппинг кластеров на URL
│   ├── run_seo_analysis.py     # SEO-анализ кластера
│   ├── run_competitor_analysis.py  # Анализ конкурентов
│   ├── fetch_yandex_queries.py # Загрузка из Яндекс.Вебмастера
│   ├── fetch_frequency.py      # Сбор частотности (Wordstat)
│   ├── collect_cluster_keywords.py # Сбор ключей для кластера
│   ├── create_cluster_from_url.py # Создание кластера по URL
│   ├── check_positions.py      # Проверка позиций
│   ├── check_all_positions.py  # Массовая проверка позиций всех ключей сайта
│   ├── run_seo_pipeline.py     # Оркестратор полного фонового SEO-анализа
│   └── scheduler.py            # Ежедневный плановый сбор
│
├── sql/
│   └── page_content.sql         # DDL для таблиц контента
│
├── tests/                       # Тесты (pytest)
│   ├── test_clustering.py        # SERP similarity + merge
│   ├── test_custom_analyzer.py   # Лемматизация, n-граммы, метрики
│   ├── test_seo_agent.py         # Pydantic-модели Structure/StructureItem
│   ├── test_pipeline_retry.py    # Retry-механизм шагов, completed_steps
│   ├── test_worker.py            # Воркер: fetch_and_schedule, run_task
│   ├── test_auth.py              # Аутентификация (hash, register, login)
│   └── test_billing.py           # Биллинг (баланс, вебхуки)
│
├── data/                        # SQLite базы (локально)
└── results/                     # Результаты кластеризации (JSON)
```

---

## 4. Модули Python (services/)

### 4.1 `cache.py` — SERPCache
**Назначение:** Кэширование результатов поисковой выдачи в MySQL для избежания повторных запросов к XMLRiver.
**Особенности:** Ключ кэша: `keyword|engine|region|device|page`, TTL: 7 дней. Использует `DBUtils.PooledDB`.

### 4.2 `clustering.py` — Алгоритм кластеризации
**Назначение:** Группировка ключевых слов по схожести выдачи Яндекса. Инкрементальная кластеризация через `serp_similarity()` (Jaccard + позиции, порог 0.4).

### 4.3 `xmlriver_client.py` — XMLRiver API
**Назначение:** Получение топа выдачи Яндекса/Google через API xmlriver.com с учетом Rate limiting (1.5с) и Exponential Backoff (коды 500 и 111).

### 4.4 `yandex_webmaster.py` — Яндекс.Вебмастер API v4
**Назначение:** Загрузка поисковых запросов из Яндекс.Вебмастера со встроенным биллингом за парсинг ключей и позиций.

### 4.7 `seo_agent.py` — LLM-агент
**Назначение:** SEO-оптимизация контента через LLM (OpenAI / Hydra AI `gpt-4o-mini`). Генерирует идеальную структуру (Pydantic модели) и переписывает HTML-текст.

### 4.10 `custom_analyzer.py` — Глубокий анализ контента
**Назначение:** Полный SEO-аудит страницы: конкуренты, лемматизация, n-граммы, технический аудит.
**Асинхронность:** Анализ конкурентов выполняется полностью асинхронно через `aiohttp` и `asyncio.gather`, заменяя старые блокирующие пулы потоков для максимальной скорости.

### 4.11 `task_manager.py` — Менеджер задач
**Назначение:** Обновление статуса (running/completed/failed) и прогресса (%) фоновых задач в БД MySQL.

### 4.12 `worker.py` — Фоновый воркер
**Назначение:** Демон, опрашивающий таблицу MySQL `tasks` раз в 2 секунды для запуска фоновых скриптов.
**Конкурентность:** Использует `threading.Lock()` для предотвращения состояния гонки (race conditions) при параллельной обработке задач. Задачи переводятся в статус `scheduled` через атомарные SQL-запросы (`UPDATE ... WHERE status='pending'`).

### 4.13 `bootstrap.py` — Точка входа скриптов
**Назначение:** Единый загрузчик окружения. Вычисляет корень проекта, меняет рабочую директорию и настраивает UTF-8 для stdout. Позволяет вызывать Python-скрипты из любого места консистентно.

---

## 5. FastAPI сервер (api/)

**Python FastAPI сервер**, обеспечивающий строгую типизацию, асинхронную обработку, безопасность и высокую производительность.

### Ключевые компоненты:

**Сессии и Аутентификация (`services/auth.py`):**
Использование JWT токенов, хранящихся в `HttpOnly` cookie.
Поддерживается плавная миграция пользователей со старой системы: реализована поддержка старых хешей (PBKDF2-SHA256). При успешном входе с устаревшим паролем, хеш автоматически обновляется до современного стандарта **bcrypt**.

**Устройство:**
- Маршрутизация (Routers): Разделение логики по доменам (`auth.py`, `sites.py`, `analysis.py`).
- Зависимости (Dependencies): Проверка авторизации через `get_current_user`.
- Static Files: Прямая раздача папки `api/public/` с помощью `StaticFiles`.
- Задачи: Эндпоинты в `analysis.py` больше не блокируют браузер, а ставят задачу в таблицу `tasks` для `worker.py`, после чего фронтенд осуществляет polling.

---

## 6. Фронтенд (HTML-страницы)

| Файл | Назначение |
|------|-----------|
| `index.html` | Дашборд: выбор сайта, запуск кластеризации, статусы |
| `cluster.html` | Управление кластерами: просмотр, поиск, маппинг |
| `sort.html` | Минус-слова, ручная сортировка ключей |
| `analysis.html` | SEO-анализ кластера: структура, SEO-план, частотность |
| `positions.html` | Мониторинг позиций |
| `cabinet.html` | Личный кабинет: баланс, биллинг, API-ключи |

**Коммуникация и Layout:**
- Используется обёртка `authFetch()` для автоматического добавления JWT токена (если он не в cookie).
- Для отображения глобальной навигации используется класс `.main-sidebar`, что предотвращает конфликты стилей с модульными боковыми панелями (например, при фильтрации кластеров).
- Отказ от хардкодных переадресаций в пользу модальных окон (например, логика добавления сайта через `showAddSiteModal()`).
- Версионирование кэша (cache busting) в HTML файлах (`style.css?v=4.2`) гарантирует своевременное обновление интерфейса.

---

## 7. База данных (MySQL)

База данных MySQL хранит всю бизнес-информацию. Доступ осуществляется через пул соединений `DBUtils.PooledDB`.

### Ключевые таблицы:
- `users`: Пользователи (в т.ч. баланс и JWT-настройки).
- `sites`: Сайты пользователей.
- `yandex_queries`: Собранные поисковые запросы.
- `cluster_mappings`: Связь кластеров с URL страниц сайта.
- `site_structure`: Дерево структуры сайта в формате JSON.
- `page_types`: Пользовательские типы страниц (название, иконка FontAwesome, цвет бейджа, описание шаблона).
- `serp_cache`: Кэш поисковой выдачи для XMLRiver (UNIQUE cache_key).
- `tasks`: Очередь фоновых задач (статус, прогресс, ошибки).
- `billing_history`: История списаний/пополнений баланса.

---

## 8. Конфигурация (.env / Config)

Все настройки приложения загружаются из `.env`. Основные параметры:
- `XMLRIVER_USER`, `XMLRIVER_KEY`, `MIRATEXT_API_KEY`, `OPENAI_API_KEY`
- База Данных: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DBNAME`
- Настройки кластеризации: `SIMILARITY_THRESHOLD = 0.4`, `CACHE_TTL_DAYS = 7`
- Конфигурация LLM: `LLM_MODEL = gpt-4o-mini`, `LLM_TEMPERATURE = 0.2`

---

## 9. Деплой

**Сервер:** Ubuntu 22.04
**Расположение:** `/home/barnick/seo-auto-cluster/`

### Инфраструктура:
1. **Nginx:** Служит reverse-proxy. Статические файлы отдаются Nginx напрямую из папки `/home/barnick/seo-auto-cluster/api/public`, что обеспечивает максимальную скорость отдачи фронтенда. Все остальные запросы (на `/api/`) проксируются на внутренний порт FastAPI.
2. **FastAPI Сервис:** Управляется `systemd` (сервис `seo-app.service`). Запускается через `uvicorn api.main:app --host 0.0.0.0 --port 3000`.
3. **Фоновый Воркер:** Фоновый процесс `worker.py` должен быть запущен параллельно (например, через отдельный systemd сервис `seo-worker.service` или `pm2`), чтобы обрабатывать очередь из БД.

### Процедура обновления:
```bash
# На сервере
cd ~/seo-auto-cluster
git pull origin main

# Обновление зависимостей (при необходимости)
source .venv/bin/activate
pip install -r requirements.txt

# Перезапуск сервисов
sudo systemctl restart seo-app.service
# sudo systemctl restart seo-worker.service
```
