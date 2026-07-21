# Архитектура и Описание Проекта seo-auto-cluster

## 1. Обзор проекта

**seo-auto-cluster** — платформа для автоматизации SEO-процессов, ориентированная на русскоязычный рынок. Объединяет веб-интерфейс на Node.js и аналитический бэкенд на Python.

**Основные функции:**
- Сбор семантического ядра (ключевых слов) из Яндекс.Вебмастера
- Кластеризация ключей по схожести поисковой выдачи (SERP) через XMLRiver
- Маппинг кластеров на страницы сайта
- SEO-анализ и генерация контента через LLM (OpenAI/Hydra) и Miratext
- Биллинговая система (списание средств за операции, пополнение через Tegro Money)
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
│              Node.js Express Server (server.js)           │
│  ├── Аутентификация (сессии в памяти)                    │
│  ├── REST API (JSON) + SSE (Server-Sent Events)          │
│  ├── spawn Python-скриптов через child_process           │
│  └── Фоновый воркер (worker.py) + ежедневный scheduler  │
└─────────────┬──────────────────────────┬─────────────────┘
              │ spawn Python             │ MySQL
              ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  Python Backend (CLI)     │  │  MySQL Database           │
│  main.py (4 режима)      │  │  ├── users                │
│  services/ (ядро)        │  │  ├── yandex_queries      │
│  nodejs-app/scripts/     │  │  ├── cluster_mappings    │
└──────────────────────────┘  │  ├── cluster_analysis    │
                              │  ├── billing_history     │
                              │  ├── tasks               │
                              │  ├── serp_cache          │
                              │  └── ...                 │
                              └──────────────────────────┘
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
│   ├── cache.py                # MySQL-кэш SERP (TTL 7 дней)
│   ├── clustering.py           # Алгоритм кластеризации (Jaccard + позиции)
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
│   └── helpers.py              # Утилиты: extract_domain, clean_url, safe_divide
│
├── nodejs-app/                 # Node.js веб-сервер + фронтенд
│   ├── server.js               # Express сервер (1927 строк, все API)
│   ├── db.js                   # MySQL pool connection
│   ├── package.json            # Node.js зависимости
│   ├── package-lock.json
│   ├── public/                 # Статические HTML-страницы
│   │   ├── index.html          # Дашборд сайтов
│   │   ├── cluster.html        # Управление кластерами
│   │   ├── sort.html           # Сортировка и минус-слова
│   │   ├── analysis.html       # SEO анализ кластера
│   │   ├── positions.html      # Мониторинг позиций
│   │   ├── cabinet.html        # Личный кабинет
│   │   ├── admin.html          # Админ-панель
│   │   ├── style.css           # Основные стили
│   │   └── semantic_layout_schema.png  # Схема разметки для SEO
│   │
│   └── scripts/                # Python-скрипты, вызываемые из Node.js
│       ├── user_auth.py        # Регистрация, логин, смена пароля
│       ├── add_site.py         # Добавление сайта
│       ├── check_domain.py     # Проверка привязки к WM
│       ├── get_sites.py        # Список сайтов пользователя
│       ├── get_keywords.py     # Получение ключей из MySQL
│       ├── update_minus.py     # Добавление минус-слов
│       ├── clear_minus.py      # Очистка минус-слов
│       ├── restore_minus.py    # Восстановление из минус-слов
│       ├── run_clustering.py   # Запуск кластеризации
│       ├── run_mapping.py      # Маппинг кластеров на URL
│       ├── run_seo_analysis.py # SEO-анализ кластера
│       ├── run_competitor_analysis.py  # Анализ конкурентов
│       ├── generate_seo_plan.py       # Генерация SEO-плана (LLM)
│       ├── generate_structure.py      # Генерация идеальной структуры
│       ├── prepare_seo_brief.py       # Подготовка брифов
│       ├── fetch_yandex_queries.py    # Загрузка из Яндекс.Вебмастера
│       ├── get_yandex_hosts.py        # Список хостов из WM
│       ├── fetch_frequency.py         # Сбор частотности (Wordstat)
│       ├── fetch_keywords.py          # Сбор ключей из Wordstat
│       ├── collect_cluster_keywords.py # Сбор ключей для кластера
│       ├── create_cluster_from_url.py # Создание кластера по URL
│       ├── check_positions.py         # Проверка позиций
│       ├── check_all_positions.py     # Массовая проверка позиций всех ключей сайта (SSE потоково)
│       ├── scheduler.py               # Ежедневный плановый сбор
│       └── get_wordstat_settings.py   # Настройки Wordstat
│
├── sql/
│   └── page_content.sql         # DDL для таблиц контента
│
├── scripts/                     # Вспомогательные скрипты
│
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
│
├── yandex_seo_pipeline/         # Отдельный пайплайн (экспериментальный)
│
├── scratch/                     # Черновики/эксперименты
│
└── html_temp/                   # HTML-шаблоны
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
  - Если похожесть >= threshold (0.4) → добавляет в кластер и пересчитывает representative SERP
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

### 4.15 `serp_collector.py` — Prefetch SERP
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

### 4.5 `cache.py` — SERPCache
*Описана выше в 4.1*

---

### 4.6 `semantic_core.py` — PostgreSQL семантическое ядро
**Назначение:** Сохранение/загрузка кластеров в PostgreSQL.

**Классы:**
- `SemanticCoreManager`
  - `save_clusters(clusters)` — TRUNCATE + bulk INSERT в `semantic_clusters`
  - `get_clusters()` — все кластеры

**Таблица:** `semantic_clusters(id SERIAL, keywords JSONB, serp_representative JSONB)`

**Используется:** `seo_workflow.py`

---

### 4.7 `miratext_client.py` — Miratext API
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

### 4.8 `seo_agent.py` — LLM-агент
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

### 4.9 `page_content_manager.py` — Управление страницами
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

### 4.10 `seo_workflow.py` — Полный SEO-цикл
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

### 4.11 `custom_analyzer.py` — Глубокий анализ контента
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

### 4.12 `task_manager.py` — Менеджер задач
**Назначение:** Обновление статуса и прогресса фоновых задач в MySQL.

**Классы:**
- `TaskManager(task_id)`
  - `update_progress(progress, result)` — `%` выполнения, опциональный JSON
  - `set_status(status, error)` — `running/completed/failed` с таймстампами

**Таблица:** `tasks(id, user_id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at)`

**Используется:** `run_clustering.py`, `run_mapping.py`, `fetch_frequency.py`

---

### 4.13 `worker.py` — Фоновый воркер
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

**Запускается:** из `server.js` через `spawn(PYTHON_PATH, [workerPath])`

---

### 4.14 helpers.py — Утилиты
**Функции:**
- `extract_domain(url)` — извлекает домен, обрабатывает IDNA (punycode)
- `clean_url(url)` — нормализует URL: убирает протокол, www, слэш
- `safe_divide(a, b, default)` — безопасное деление

---

## 5. Node.js сервер (server.js)

**Express-сервер** на порту 3000, ~1927 строк.

### Ключевые компоненты:

**Сессии:** In-memory объект `sessions{}` — `session_id → {user_id, username}`

**Middlewares:**
- `authenticate` — проверка `Authorization: session_id`, проверка `is_blocked`
- `authenticateAdmin` — проверка Bearer-токена администратора

**Helpers:**
- `callPython(scriptPath, args, stdin)` — spawn Python, возвращает Promise<string>
- `normalizeUrl(url)` — strip protocol + trailing slash
- `checkAndDeductBalance(userId, amount, description)` — транзакция: списание + billing_history
- `getSystemSettings()` — тарифы из таблицы `settings`

### API Endpoints:

**Аутентификация:**
- `POST /api/auth/register` — регистрация
- `POST /api/auth/login` — логин
- `GET /api/auth/session` — проверка сессии
- `POST /api/auth/logout` — выход

**Пользователи и сайты:**
- `GET /api/user-info` — баланс
- `GET /api/user/settings` — настройки + список сайтов
- `POST /api/user/settings` — обновление Yandex token
- `POST /api/user/change-password` — смена пароля
- `POST /api/sites` — добавить сайт (с проверкой WM)
- `GET /api/sites` — список сайтов

**Ключевые слова и кластеризация:**
- `GET /api/keywords` — ключи (фильтр по domain)
- `POST /api/run-clustering` — запуск кластеризации (синхронный)
- `POST /api/move-keywords` — перемещение между кластерами
- `POST /api/delete-cluster` — удаление кластера
- `POST /api/disband-cluster` — расформирование кластера
- `POST /api/minus-words` — добавить в минус-слова
- `POST /api/restore-minus` — восстановить из минус-слов
- `POST /api/clear-minus` — очистить минус-слова

**Маппинг:**
- `GET /api/run-mapping-stream` — SSE-стрим (прогресс в реальном времени)
- `POST /api/run-mapping` — синхронный маппинг
- `GET /api/run-mapping-single` — маппинг одного кластера
- `POST /api/save-mapping-manual` — ручное указание URL
- `GET /api/mappings` — все маппинги
- `POST /api/cluster/target-url` — обновление целевого URL

**Мониторинг позиций:**
- `GET /api/positions/history` — история позиций по сайту/кластеру
- `GET /api/positions/run-stream` — SSE-стрим массовой проверки позиций (`check_all_positions.py`)
- `GET /api/positions/check` — разовая проверка одного кластера (`check_positions.py`)

**SEO-анализ и контент:**
- `POST /api/cluster/run-seo-analysis` — SEO-анализ кластера
- `GET /api/analysis-status` — проверка, идёт ли анализ
- `GET /api/analysis` — результаты анализа
- `POST /api/cluster/generate-structure` — генерация структуры через LLM
- `POST /api/cluster/save-structure` — сохранение структуры (с историей)
- `POST /api/seo-history/generate` — генерация SEO-плана
- `GET /api/seo-history/dates` — даты сохранённых планов
- `GET /api/seo-history/plan` — SEO-план по дате
- `GET /api/prepare-seo-brief` — SEO-бриф
- `POST /api/cluster/remove-lsi` — удаление LSI (в минус)

**Позиции:**
- `GET /api/cluster/check-positions-stream` — SSE-проверка позиций
- `POST /api/cluster/check-positions` — синхронная проверка

**Конкуренты:**
- `GET /api/run-competitor-analysis-stream` — SSE-анализ конкурентов
- `POST /api/run-competitor-analysis` — синхронный
- `GET /api/run-competitor-analysis-single` — для одного кластера

**Кластеры:**
- `POST /api/create-cluster-by-url` — создание кластера по URL
- `POST /api/update-keyword-text` — редактирование ключа
- `POST /api/collect-keywords-for-cluster` — сбор ключей для кластера
- `POST /api/update-cluster-name` — переименование
- `POST /api/toggle-cluster-favorite` — избранное
- `POST /api/toggle-cluster-pinned` — закрепление
- `POST /api/update-pinned-order` — порядок закреплённых
- `GET /api/cluster-names` — метаданные кластеров
- `GET /api/cluster-lsi` — LSI-слова кластера

**Частотность (Wordstat):**
- `GET /api/run-frequency-stream` — запуск сбора частотности (через tasks)
- `GET /api/frequency-status` — статус задачи
- `GET /api/tasks/:id` — статус конкретной задачи
- `GET /api/wordstat-settings` — настройки сбора
- `POST /api/wordstat-settings` — сохранение настроек
- `DELETE /api/wordstat-settings/:id` — удаление настройки

**Яндекс.Вебмастер:**
- `GET /api/fetch-wm-queries` — загрузка запросов
- `GET /api/get-wm-hosts` — список хостов
- `POST /api/check-domain` — проверка привязки

**Биллинг:**
- `POST /api/create-payment` — создание платежа (Tegro Money)
- `POST /api/payment-callback` — вебхук от Tegro
- `GET /api/billing-history` — история операций

**Админ:**
- `POST /api/admin/login`
- `GET /api/admin/tariffs` / `POST /api/admin/tariffs/update`
- `GET /api/admin/users` / `POST /api/admin/users/update`
- `GET /api/admin/sites`
- `GET /api/admin/payments`
- `GET /api/admin/logs`

**Прочее:**
- `GET /api/geo-regions` — регионы из yandex_geo.csv
- `GET /api/user/settings` — yandex_region_id
- `GET /api/test-seo-2026` — тест экспериментального пайплайна

**Фоновые задачи:**
- `startBackgroundTasks()` — запускает `worker.py` и `scheduler.py` (каждые 24ч)
- `runScheduler()` — ежедневный сбор данных для всех пользователей

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
| `TEGRO_SHOP_ID` | фикс. ID | ID магазина Tegro Money |
| `TEGRO_SECRET_KEY` | — | Секрет Tegro |

### Логика выбора БД:
1. Если `PG_PASSWORD` задан → PostgreSQL
2. Иначе если `MYSQL_HOST` + `MYSQL_USER` → MySQL
3. Иначе → SQLite

---

## 9. Внешние интеграции

| Сервис | Протокол | Назначение |
|--------|---------|-----------|
| **XMLRiver** | REST (XML) | SERP Яндекса/Google |
| **Яндекс.Вебмастер** | REST v4 (JSON) | Поисковые запросы сайта |
| **Miratext** | REST (JSON) | SEO-анализ текста |
| **OpenAI / Hydra AI** | REST (JSON) | LLM для контента |
| **Tegro Money** | REST (JSON) | Приём платежей |

---

## 10. Деплой

### Сервер (Ubuntu 22.04, user `barnick`):

**Расположение:**
- Git-репо: `~/seo-auto-cluster/`
- Рабочая копия Python: `~/` (файлы дублируются из репо)
- Node.js: запущен из `~/seo-auto-cluster/nodejs-app/`

**Процессы:**
- Node.js: `nohup node server.js > server.log 2>&1 &` (PID ~389345)
- MySQL: Docker (`docker-compose.yml`), порт 3306

**Обновление:**
```bash
# Локально
git add . && git commit -m "type: description" && git push

# На сервере
cd ~/seo-auto-cluster && git pull
# Копировать в ~/ если нужно:
cp services/*.py ~/services/
cp nodejs-app/server.js ~/nodejs-app/
# Перезапустить:
kill <PID> && cd ~/seo-auto-cluster/nodejs-app && nohup node server.js > server.log 2>&1 &
```

**Node.js:** v20.20.2
**Python:** 3.12.3
**Git:** 2.43.0
