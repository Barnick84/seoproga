# Архитектура и Описание Проекта seo-auto-cluster

## 1. Обзор проекта

**seo-auto-cluster** — платформа для автоматизации SEO-процессов, ориентированная на русскоязычный рынок. Это полностью Python-инфраструктура, объединяющая веб-интерфейс на базе FastAPI (встроенная раздача статики) и мощный аналитический бэкенд.

**Основные функции:**
- Сбор семантического ядра (ключевых слов) из Яндекс.Вебмастера
- Кластеризация ключей по схожести поисковой выдачи (SERP) через XMLRiver
- Маппинг кластеров на страницы сайта
- SEO-анализ и генерация контента через LLM (OpenAI/Hydra) и Miratext
- Биллинговая система (списание средств за операции, пополнение через Cardlink)
- Фоновый воркер для длительных задач (частотность, кластеризация)

---

## 2. Архитектура и Data Flow

```
┌──────────────────────────────────────────────────────────┐
│                   Browser (Frontend)                      │
│  index.html | cluster.html | sort.html | analysis.html   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI Server (api/main.py)                 │
│  ├── Аутентификация (JWT + HttpOnly Cookies)             │
│  ├── REST API (JSON) + SSE (Server-Sent Events)          │
│  ├── Раздача статических файлов (api/public)             │
│  └── Вызов Python-скриптов и сервисов напрямую            │
└─────────────┬──────────────────────────┬─────────────────┘
              │ async exec               │ MySQL
              ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  Python Backend (CLI)     │  │  MySQL Database           │
│  main.py (4 режима)      │  │  ├── users                │
│  services/ (ядро)        │  │  ├── yandex_queries      │
│  scripts/ (фоновые)      │  │  ├── cluster_mappings    │
└──────────────────────────┘  │  ├── cluster_analysis    │
                              │  ├── billing_history     │
                              │  ├── tasks               │
                              │  ├── serp_cache          │
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
6. worker.py → MySQL tasks → spawn scripts → TaskManager.update_progress()
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
│   ├── __init__.py
│   ├── cache.py                # MySQL-кэш SERP (TTL 7 дней), lazy connection
│   ├── clustering.py           # Алгоритм кластеризации (Jaccard + позиции), инкрементальный merge
│   ├── custom_analyzer.py      # Глубокий SEO-анализ контента
│   ├── miratext_client.py      # Клиент Miratext API
│   ├── page_content_manager.py # Управление контентом страниц (PostgreSQL)
│   ├── semantic_core.py        # Хранение сем. ядра (PostgreSQL)
│   ├── seo_agent.py            # LLM-агент (OpenAI/Hydra)
│   ├── seo_workflow.py         # Оркестратор полного SEO-цикла
│   ├── task_manager.py         # Менеджер прогресса задач (MySQL)
│   ├── worker.py               # Фоновый воркер задач
│   ├── serp_collector.py       # Prefetch SERP с прогрессом (отдельный сбор до кластеризации)
│   ├── xmlriver_client.py      # Клиент XMLRiver API (rate limiting 1.5с)
│   └── yandex_webmaster.py     # Клиент Яндекс.Вебмастер API v4
│
├── utils/
│   ├── bootstrap.py             # Единая точка входа скриптов (chdir, sys.path, stdout)
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
│   │   ├── analysis.py         # Кластеризация, маппинг, частотность (SSE), задачи
│   │   ├── billing.py          # Cardlink платежи и вебхуки
│   │   ├── admin.py            # Админ-панель (тарифы, пользователи, логи)
│   │   ├── cluster.py          # Кластеры: маппинг, LSI, SEO-история, структура
│   │   ├── wordstat.py         # Настройки Wordstat, регионы
│   │   └── positions.py        # Мониторинг позиций (SSE потоки)
│   │
│   └── public/                 # Статические HTML-страницы (раздаются сервером)
│       ├── index.html          # Дашборд сайтов
│       ├── cluster.html        # Управление кластерами
│       ├── sort.html           # Сортировка и минус-слова
│       ├── analysis.html       # SEO анализ кластера
│       ├── positions.html      # Мониторинг позиций
│       ├── cabinet.html        # Личный кабинет
│       ├── admin.html          # Админ-панель
│       ├── style.css           # Основные стили
│       └── semantic_layout_schema.png  # Схема разметки для SEO
│
├── scripts/                    # Python-скрипты для фоновых задач
│   ├── user_auth.py            # Утилиты auth
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
│   ├── scheduler.py            # Ежедневный плановый сбор
│   └── ...
│
├── sql/
│   └── page_content.sql         # DDL для таблиц контента

├── tests/                       # Тесты (pytest)
│
├── data/                        # SQLite базы (локально)
│   ├── serp_cache.db
│   ├── yandex_queries.db
│   ├── seo_workflow.db
│   ├── sites.db
│   └── users.db
│
├── results/                     # Результаты кластеризации (JSON)
```

---

## 4. Модули Python (services/)

### 4.1 `cache.py` — SERPCache
**Назначение:** Кэширование результатов поисковой выдачи в MySQL для избежания повторных запросов к XMLRiver.

**Классы:**
- `SERPCache` — `get(keyword, engine, region)` / `set(keyword, urls, engine, region)`
  - Ключ кэша: `keyword|engine|region|device|page`
  - TTL: `Config.CACHE_TTL_DAYS` (7 дней)
  - Таблица: `serp_cache` (MySQL) с upsert (`ON DUPLICATE KEY UPDATE`)
  - Хранит URL-списки в JSON (колонка `urls TEXT`)
  - Используется контекстный менеджер `get_db_cursor` и пул соединений `PooledDB` для надежной работы при высокой нагрузке.

**Используется:** `XmlriverClient.fetch_serp()`

---

### 4.2 `clustering.py` — Алгоритм кластеризации
**Назначение:** Группировка ключевых слов по схожести выдачи Яндекса.

**Функции:**
- `serp_similarity(urls_a, urls_b) → float`
  - Композитная метрика: 0.7 × Jaccard + 0.3 × weighted position similarity
  - Jaccard: размер пересечения / размер объединения
  - Weighted: сумма весов совпавших позиций (ранний URL = больший вес)
- `merge_serps(serps_list) → list[str]`
  - Склеивает несколько SERP-списков, сортируя по частоте появления / позиции
  - Возвращает топ-30 URL
- `cluster_keywords(keywords, client, threshold, initial_clusters) → list[dict]`
  - Инкрементальная кластеризация: для каждого ключа получает SERP
  - Сравнивает с существующими кластерами через `serp_similarity()`
  - Если похожесть >= threshold (0.4) → добавляет в кластер и пересчитывает representative SERP (merge нового SERP с существующим, O(1), без N+1 re-fetch)
  - Иначе → создаёт новый кластер
  - Пропущенные ключи (пустой SERP) логируются (`skipped`)

**Параметры:**
- `SIMILARITY_THRESHOLD = 0.4`
- `SERP_TOP_N = 10`

**Используется:** `run_clustering.py`, `seo_workflow.py`, `main.py`

---

### 4.3 `xmlriver_client.py` — XMLRiver API
**Назначение:** Получение топа выдачи Яндекса/Google через API xmlriver.com.

**Классы:**
- `XmlriverClient`
  - `min_delay: float` — минимальная пауза между запросами (`Config.XMLRIVER_REQUEST_DELAY`, по умолч. 1.5с)
  - `_last_request: float` — таймстамп последнего запроса (для rate limiting)
  - `fetch_serp(keyword, engine, region, device, top_n, page, use_cache, retries) → list[str]`
    - Проверяет кэш (если `use_cache=True`)
    - **Rate limiting**: если с прошлого запроса прошло < `min_delay` — ждёт остаток
    - Строит params: `user`, `key`, `query` (с `&` → `%26`), `groupby`, `lr`/`loc`, `page`, `device`
    - XML-ответ парсится: извлекаются `doc` с `contenttype=organic`
    - Retry: ошибка 500 («перезапрос») — пауза 5с; **ошибка 111** («нет каналов») — exponential backoff 10с/20с/30с
    - После успеха → сохраняет в кэш
  - `_parse_xmlriver_response(data)` — парсит XML, исключая дубликаты
  - `_get_error_info(data)` — извлекает `@code` и `#text` ошибки
  - `_is_retry_needed(data)` — проверяет коды 500 и 111

**Rate limiting:** все вызовы `fetch_serp()` (кроме кэш-хитов) проходят через `time.sleep(min_delay - elapsed)`. Это предотвращает перегрузку каналов XMLRiver при массовом сборе SERP (800+ запросов).

**Обработка ошибок:**
- **111**: Нет свободных каналов — retry с ожиданием до 30с, до 5 попыток
- **500**: Перезапрос — retry с ожиданием 5с
- При исчерпании попыток → пустой список + сообщение в stdout

**Используется:** `clustering.py`, `custom_analyzer.py`, `seo_workflow.py`, `serp_collector.py`

---

### 4.14 `serp_collector.py` — Prefetch SERP
**Назначение:** Пакетный сбор SERP для кластеризации с прогрессом. Отделяет фазу сбора данных от фазы вычислений.

**Функции:**
- `prefetch_for_clustering(keywords, client, on_progress) → int`
  - Для каждого ключа: `fetch_serp(use_cache=True)` — проверяет кэш
  - Если не в кэше — API-запрос с rate limiting (через `XmlriverClient`)
  - `on_progress(done, total)` — колбэк для обновления прогресса (TaskManager)
  - Возвращает количество ключей, найденных в кэше

**Логика:** prefetch прогоняет все ключи через `client.fetch_serp()`. Каждый успешный запрос попадает в кэш. После prefetch `cluster_keywords()` работает только из кэша (`skip_cache_miss=True`), без единого вызова API.

**Используется:** `run_clustering.py`

---

### 4.4 `yandex_webmaster.py` — Яндекс.Вебмастер API v4
**Назначение:** Загрузка поисковых запросов из Яндекс.Вебмастера с биллингом.

**Классы:**
- `YandexWebmasterClient`
  - `__init__(token, user_id)` — OAuth-сессия
  - `_get_user_id()` → Yandex user ID
  - `list_hosts()` → все сайты пользователя
  - `fetch_queries_recent(site_url)` → популярные запросы за 14 дней (лимит 500)
  - `save_queries_to_db(queries)` → upsert в `yandex_queries`, списание средств
  - `get_unique_queries_for_clustering(site_url)` → уникальные запросы без минус-слов
  - `calculate_position_cost(pos, step_rate)` → стоимость по позиции

**Биллинг:**
- Новый запрос: `position_new_rate` (0.25₽)
- Существующий: `ceil(pos/10) × position_step_rate` (0.05₽)
- Списание: `UPDATE users SET balance = balance - cost`

**Используется:** `seo_workflow.py`, `main.py`, `streamlit_app.py`

---

### 4.5 `semantic_core.py` — PostgreSQL семантическое ядро
**Назначение:** Сохранение/загрузка кластеров в PostgreSQL.

**Классы:**
- `SemanticCoreManager`
  - `save_clusters(clusters)` — TRUNCATE + bulk INSERT в `semantic_clusters`
  - `get_clusters()` — все кластеры

**Таблица:** `semantic_clusters(id SERIAL, keywords JSONB, serp_representative JSONB)`

**Используется:** `seo_workflow.py`

---

### 4.6 `miratext_client.py` — Miratext API
**Назначение:** SEO-анализ текста через miratext.ru.

**Классы:**
- `MiratextClient`
  - `analyze(text, keywords)` → submit + poll до готовности
  - `submit_analysis(text, keywords)` → POST /api2, получает task_id
  - `get_result(task_id)` → GET /api2 до статуса `success` или timeout
  - `_parse_recommendations(raw, target_keywords)` → частотность ключей

**API:** `https://miratext.ru/api2`

**Параметры:**
- `MIRATEXT_MAX_WAIT = 180с`
- `MIRATEXT_POLL_INTERVAL = 3с`

**Используется:** `seo_workflow.py`, `main.py`

---

### 4.7 `seo_agent.py` — LLM-агент
**Назначение:** SEO-оптимизация контента через LLM (OpenAI / Hydra AI).

**Классы:**
- `SEOAgent`
  - `rewrite_page(url, editable_html, keywords, miratext_data)` → оптимизированный HTML
  - `generate_ideal_structure(competitors_headers)` → идеальная H2-H3 структура
  - `_build_prompt(url, html, keywords, rec)` → формирует промпт с требованиями
  - `_clean_llm_output(text)` → удаляет markdown-блоки из ответа LLM

**Модель:** `gpt-4o-mini` (через Hydra AI /api/hydraai.ru/v1)
**Параметры:** temperature 0.2, max_tokens 8192

**Используется:** `seo_workflow.py`, `main.py`

---

### 4.8 `page_content_manager.py` — Управление страницами
**Назначение:** Загрузка, парсинг, версионирование контента страниц.

**Классы:**
- `PageContentManager`
  - `fetch_and_parse_page(url)` → HTTP GET + BeautifulSoup → делит на editable/non-editable
  - `split_editable_content(html)` — извлекает `<main>`, `<article>`, `<div class="content">`
  - `save_page(url, full_html, editable_html, non_editable_html)` — upsert
  - `save_version(url, editable_html, keywords)` — сохраняет версию
  - `get_pending_tasks()` — очередь SEO-задач
  - `merge_html(editable, non_editable)` — сборка полного HTML

**Хранилище:** PostgreSQL (`page_content`, `page_versions`, `seo_tasks`)

**Используется:** `seo_workflow.py`, `main.py`

---

### 4.9 `seo_workflow.py` — Полный SEO-цикл
**Назначение:** Оркестратор полного пайплайна из 4 шагов.

**Классы:**
- `SEOWorkflow`
  - `run_full_workflow()`:
    1. **get_cluster_keywords()** — Yandex WM → кластеризация → SemanticCore
    2. **map_clusters_to_pages()** — SERP-похожесть каждой страницы с каждым кластером
    3. Miratext-анализ контента
    4. LLM-оптимизация и сохранение версии
  - `_save_mapping(page_url, cluster_id, keywords)` — сохраняет в `page_cluster_mapping`
  - `get_mappings()` — все маппинги

**Маппинг:** для каждого кластера ищет страницу на сайте с максимальной SERP-похожестью (порог >= 0.15)

**Поддержка:** SQLite (dev) и PostgreSQL (prod) для `page_cluster_mapping`

---

### 4.10 `custom_analyzer.py` — Глубокий анализ контента
**Назначение:** Полный SEO-аудит страницы: сбор конкурентов, лемматизация, n-граммы, технический аудит, определение интента.

**Классы:**
- `CustomAnalyzer`
  - `analyze_content(html, url)` — метрики текста, title, h1-h6, density
  - `fetch_competitors(keywords)` — топ-10 конкурентов через XMLRiver
  - `calculate_complexity_metrics(lemmas, text)` — stuffing, wateriness, Zipf
  - `get_intent(lemmas)` — коммерческий/информационный/смешанный интент
  - `run_technical_audit(html, url)` — HTTPS, schema.org, заголовки, alt, семантические теги
  - `process_analysis(target_url, keywords, raw_html, competitor_urls)` — сравнительный анализ
  - `extract_meta_and_headers(html)` — title, meta description, H1-H6 иерархия
  - `generate_ngrams(lemmas, n)` — биграммы и триграммы
  - `get_lemmas(text)` — токенизация + лемматизация (pymorphy3) + стоп-слова

**Зависимости:** pymorphy3, BeautifulSoup, numpy

---

### 4.11 `task_manager.py` — Менеджер задач
**Назначение:** Обновление статуса и прогресса фоновых задач в MySQL.

**Классы:**
- `TaskManager(task_id)`
  - `update_progress(progress, result)` — `%` выполнения, опциональный JSON
  - `set_status(status, error)` — `running/completed/failed` с таймстампами

**Таблица:** `tasks(id, user_id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at)`

**Используется:** `run_clustering.py`, `run_mapping.py`, `fetch_frequency.py`

---

### 4.12 `worker.py` — Фоновый воркер
**Назначение:** Демон, polling MySQL `tasks` раз в 2 секунды, запуск скриптов.

**Функции:**
- `main()` — бесконечный цикл:
  1. `get_pending_tasks()` — SELECT ... WHERE status='pending' LIMIT 5
  2. Каждую задачу → `status='scheduled'` (чтобы другие worker'ы не подхватили)
  3. `run_task(task)` — spawn соответствуещего Python-скрипта

**Маппинг задач:**
| task_type | script |
|-----------|--------|
| frequency | `fetch_frequency.py` |
| clustering | `run_clustering.py` |
| mapping | `run_mapping.py` |
| competitor_analysis | `run_competitor_analysis.py` |
| fetch_queries | `fetch_yandex_queries.py` |

**Запускается:** из `worker.py` (автономный процесс)

---

### 4.13 bootstrap.py — Точка входа скриптов
**Назначение:** Единый загрузчик для скриптов, вызываемых из Node.js. Заменяет 8 строк идентичного boilerplate в каждом из 26 скриптов одной строчкой `from utils.bootstrap import bootstrap; bootstrap()`.

**Действия `bootstrap()`:**
1. Вычисляет `project_root` от своего `__file__` (на 3 уровня выше)
2. `os.chdir(project_root)` — все относительные пути работают от корня проекта
3. Добавляет `project_root` в `sys.path` (если ещё не добавлен)
4. На Windows: настраивает `sys.stdout`/`sys.stderr` на UTF-8 (через `reconfigure()` или `TextIOWrapper`)

**Затронутые файлы:** Все 26 скриптов в `nodejs-app/scripts/`. Экономия: ~160 строк кода.

### 4.14 helpers.py — Утилиты
**Функции:**
- `extract_domain(url)` — извлекает домен, обрабатывает IDNA (punycode)
- `clean_url(url)` — нормализует URL: убирает протокол, www, слэш
- `safe_divide(a, b, default)` — безопасное деление

---

## 5. FastAPI сервер (api/)

**Python FastAPI сервер**, обеспечивающий строгую типизацию, асинхронную обработку и высокую производительность.

### Ключевые компоненты:

**Сессии и Аутентификация:** Использование JWT токенов, хранящихся в `HttpOnly` cookie.

**Устройство:**
- Маршрутизация (Routers): Разделение логики по доменам (`auth.py`, `sites.py`, `billing.py`, `analysis.py`).
- Зависимости (Dependencies): Проврка аутентификации через `get_current_user`, получение сессий БД, и т.д.
- Static Files: Прямая раздача папки `api/public/` с помощью `StaticFiles`.

**Потоковые ответы (SSE):**
FastAPI `StreamingResponse` используется вместо старых потоков Node.js, позволяя выводить прогресс скриптов `scripts/` в реальном времени.

**Фоновые задачи и Безопасность:**
- `worker.py` и `scheduler.py` управляются отдельно, читая очередь задач из таблицы `tasks`. Синхронные операции воркера обернуты в `asyncio.to_thread`, чтобы не блокировать event loop.
- Для предотвращения race conditions при запуске задач из БД используется механизм `Auto-Retry` с экспоненциальной задержкой.
- Биллинговые вебхуки защищены атомарными SQL-транзакциями с использованием `SELECT ... FOR UPDATE`, обеспечивая идемпотентность и безопасность финансов.
- Защита от XSS в статических страницах (например, в `mane.html`) реализована через экранирование пользовательского ввода (`escapeHtml`).
- Взаимодействие с внешними API (например, XMLRiver) включает строгую обработку фатальных ошибок без их маскировки, с выбросом исключений при невозможности повтора.

---

## 6. Фронтенд (HTML-страницы)

| Файл | Назначение |
|------|-----------|
| `index.html` | Дашборд: выбор сайта, запуск кластеризации, статусы |
| `cluster.html` | Управление кластерами: просмотр, перемещение ключей, поиск, маппинг, создание по URL |
| `sort.html` | Минус-слова, восстановление, ручная сортировка ключей |
| `analysis.html` | SEO-анализ кластера: структура H2-H3, SEO-план, частотность, история версий |
| `positions.html` | Мониторинг/проверка позиций |
| `cabinet.html` | Личный кабинет: баланс, биллинг, API-ключи |
| `admin.html` | Админ-панель: пользователи, тарифы, логи, платежи |

**Авторизация:** session_id в `localStorage`, передаётся в заголовке `Authorization`.

**Коммуникация:**
- `authFetch()` — обёртка над `fetch()` с автоматическим добавлением session_id
- SSE для операций с прогрессом (маппинг, проверка позиций, анализ конкурентов)
- Polling для задач (частотность, SEO-анализ)

---

## 7. База данных (MySQL)

### Таблицы:

| Таблица | Назначение | Ключевые колонки |
|---------|-----------|------------------|
| `users` | Пользователи | `id, username, email, password, balance, yandex_token, is_blocked` |
| `sites` | Сайты пользователей | `id, user_id, domain` |
| `yandex_queries` | Ключевые слова | `id, user_id, site_url, query, hits, clicks, ctr, avg_position, clustered, minus_word, frequency, fetched_at` |
| `cluster_mappings` | Маппинг кластер→URL | `user_id, site_url, cluster_id, target_url` |
| `cluster_analysis` | SEO-анализ (JSONB) | `user_id, site_url, cluster_id, analysis_data (JSON)` |
| `cluster_seo_history` | История SEO-планов | `user_id, site_url, cluster_id, analysis_date, intent_type, seo_plan_content, optimized_html` |
| `cluster_names` | Метаданные кластеров | `user_id, site_url, cluster_id, cluster_name, is_favorite, is_pinned, pinned_order` |
| `cluster_lsi` | LSI-слова | `user_id, site_url, cluster_id, keyword, frequency` |
| `serp_cache` | Кэш SERP | `cache_key (UNIQUE), urls (JSON), fetched_at (datetime)` |
| `tasks` | Фоновые задачи | `id, user_id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at` |
| `billing_history` | История списаний | `user_id, amount, description, type (charge/deposit), created_at` |
| `payment_history` | Платежи (Tegro) | `user_id, amount, order_id, status (pending/success), created_at` |
| `settings` | Тарифы | `key (UNIQUE), value` |
| `wordstat_settings` | Настройки Wordstat | `user_id, name, device, region, region_name, is_default` |
| `user_settings` | Настройки пользователя | `user_id, yandex_region_id` |
| `token_blacklist` | JWT отзыв (jti + expires_at) | `jti (PK), expires_at, created_at` |
| `query_history` | История позиций | `user_id, site_url, query, position, engine, device, created_at` |

### PostgreSQL таблицы (опционально):
- `semantic_clusters` — кластеры (JSONB)
- `page_content`, `page_versions`, `seo_tasks` — контент страниц

### SQLite (dev/локально):
- `serp_cache.db` — кэш SERP
- `yandex_queries.db` — ключи
- `seo_workflow.db` — маппинги
- `sites.db` — сайты
- `users.db` — пользователи

---

## 8. Конфигурация (.env / Config)

| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `XMLRIVER_USER` | — | ID пользователя XMLRiver |
| `XMLRIVER_KEY` | — | API-ключ XMLRiver |
| `XMLRIVER_REGION` | 213 | Регион (213 = Москва) |
| `XMLRIVER_ENGINE` | yandex | Поисковик: yandex/google |
| `YANDEX_OAUTH_TOKEN` | — | OAuth-токен Яндекса |
| `YANDEX_SITE_URL` | — | Дефолтный сайт для CLI |
| `SIMILARITY_THRESHOLD` | 0.4 | Порог похожести SERP |
| `CACHE_TTL_DAYS` | 7 | TTL кэша SERP |
| `XMLRIVER_REQUEST_DELAY` | 1.5 | Мин. пауза между запросами XMLRiver (сек) |
| `MIRATEXT_API_KEY` | — | API-ключ Miratext |
| `OPENAI_API_KEY` | — | Ключ OpenAI/Hydra |
| `LLM_MODEL` | gpt-4o-mini | Модель LLM |
| `LLM_TEMPERATURE` | 0.2 | Температура LLM |
| `LLM_MAX_TOKENS` | 8192 | Макс. токенов |
| `BASE_URL` | https://api.openai.com/v1 | Базовый URL API |
| `MYSQL_HOST` | localhost | Хост MySQL |
| `MYSQL_PORT` | 3306 | Порт MySQL |
| `MYSQL_DBNAME` | seo_auto | БД MySQL |
| `MYSQL_USER` | root | Пользователь MySQL |
| `MYSQL_PASSWORD` | — | Пароль MySQL |
| `PG_PASSWORD` | — | Пароль PostgreSQL (если задан — используется PG) |
| `CARDLINK_SHOP_ID` | фикс. ID | ID магазина Cardlink |
| `CARDLINK_TOKEN` | — | Секрет Tegro |

### Логика выбора БД:
1. Подключения к БД управляются через `DBUtils.PooledDB` (`maxconnections=20`, `blocking=True`) в `config.py` для предотвращения исчерпания лимитов соединений.
2. Если `PG_PASSWORD` задан → PostgreSQL
3. Иначе если `MYSQL_HOST` + `MYSQL_USER` → MySQL
4. Иначе → SQLite

---

## 9. Внешние интеграции

| Сервис | Протокол | Назначение |
|--------|---------|-----------|
| **XMLRiver** | REST (XML) | SERP Яндекса/Google |
| **Яндекс.Вебмастер** | REST v4 (JSON) | Поисковые запросы сайта |
| **Miratext** | REST (JSON) | SEO-анализ текста |
| **OpenAI / Hydra AI** | REST (JSON) | LLM для контента |
| **Cardlink** | REST (JSON) | Приём платежей |

---

## 10. Деплой

### Сервер (Ubuntu 22.04, user `barnick`):

**Расположение:**
- Git-репо: `~/seo-auto-cluster/`
- Виртуальное окружение Python (venv) с зависимостями из `requirements.txt`

**Процессы:**
- Управление процессами лучше всего выполнять через `systemd`, `pm2` или `nohup`.
- Запуск FastAPI: `uvicorn api.main:app --host 0.0.0.0 --port 3000`
- MySQL: Docker (`docker-compose.yml`), порт 3306

**Обновление:**
```bash
# Локально
git add . && git commit -m "type: description" && git push

# На сервере
cd ~/seo-auto-cluster && git pull
# Активация окружения и установка зависимостей:
source .venv/bin/activate
pip install -r requirements.txt
# Перезапуск сервиса (зависит от вашей системы):
# Если используете systemctl:
sudo systemctl restart fastapi-seo
```

**Python:** 3.10+ (рекомендуется 3.12+)
**Git:** 2.43.0
