# streamlit_app.py
import streamlit as st
import sqlite3

from config import Config
from services.cache import SERPCache
from services.xmlriver_client import XmlriverClient
from services.clustering import cluster_keywords as cluster_keywords_func
from services.yandex_webmaster import YandexWebmasterClient

st.set_page_config(
    page_title="SEO Auto Cluster",
    page_icon="🔍",
    layout="wide",
)

if "clusters" not in st.session_state:
    st.session_state.clusters = []
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = []
if "minus_words" not in st.session_state:
    st.session_state.minus_words = []
if "selected_keywords" not in st.session_state:
    st.session_state.selected_keywords = set()
if "unclustered" not in st.session_state:
    st.session_state.unclustered = []


def normalize_site_url(url: str) -> str:
    url = url.lower().strip()
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    elif url.startswith("http:"):
        url = url[5:]
    elif url.startswith("https:"):
        url = url[6:]
    url = url.rstrip("/")
    return url


def get_wm_queries_from_db(site_url: str = "", min_hits: int = 0) -> list:
    if not site_url:
        site_url = st.session_state.get("site_url", Config.YANDEX_SITE or "")

    db_path = "data/yandex_queries.db"
    try:
        with sqlite3.connect(db_path) as conn:
            if site_url:
                site_url = normalize_site_url(site_url)
                # Try exact and partial match
                cur = conn.execute(
                    "SELECT query, hits FROM yandex_queries "
                    "WHERE site_url = ? OR site_url LIKE ? ORDER BY hits DESC",
                    (site_url, f"%{site_url}%"),
                )
                rows = cur.fetchall()
                if not rows:
                    # Show all queries as fallback
                    cur = conn.execute(
                        "SELECT query, hits FROM yandex_queries ORDER BY hits DESC"
                    )
                    rows = cur.fetchall()
            else:
                # No site_url - show all
                cur = conn.execute(
                    "SELECT query, hits FROM yandex_queries ORDER BY hits DESC"
                )
                rows = cur.fetchall()

            # Filter by min_hits only if we have non-zero hits in data
            non_zero_hits = any(h for _, h in rows if h > 0)
            if non_zero_hits and min_hits > 0:
                rows = [(q, h) for q, h in rows if h >= min_hits]

            return [{"query": row[0], "hits": row[1]} for row in rows]
    except Exception as e:
        st.error(f"DB error: {e}")
        return []


def main():
    st.title("🔍 SEO Auto Cluster")
    st.markdown("Кластеризация ключевых слов по SERP-похожести")

    tab1, tab2, tab3 = st.tabs(["📊 Кластеризация", "📥 Данные WM", "⚙️ Настройки"])

    with tab1:
        render_clustering_tab()
    with tab2:
        render_data_tab()
    with tab3:
        render_settings_tab()


def render_clustering_tab():
    st.subheader("Кластеризация ключевых слов")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("#### 1. Выберите источник ключевых слов")

        source = st.radio(
            "Источник:",
            ["Из Яндекс Вебмастера", "Свои ключи", "Оба источника"],
            horizontal=True,
        )

        keywords = []
        if source in ["Из Яндекс Вебмастера", "Оба источника"]:
            site_url = st.session_state.get("site_url", Config.YANDEX_SITE)
            min_hits = st.session_state.get("min_hits", 5)
            wm_queries = get_wm_queries_from_db(site_url, min_hits)
            wm_keywords = [q["query"] for q in wm_queries]
            keywords.extend(wm_keywords)
            if wm_keywords:
                st.success(f"✅ Загружено из WM: {len(wm_keywords)} запросов")

        if source in ["Свои ключи", "Оба источника"]:
            custom_input = st.text_area(
                "Свои ключевые слова (по одному на строке)",
                height=150,
                placeholder="купить iphone 15\niphone 15 pro\nайфон 15",
            )
            if custom_input:
                custom_kw = [k.strip() for k in custom_input.split("\n") if k.strip()]
                keywords.extend(custom_kw)
                st.success(f"✅ Добавлено своих: {len(custom_kw)} запросов")

        st.markdown("#### 2. Минус-слова (опционально)")

        minus_input = st.text_area(
            "Минус-слова (по одному на строке, будут исключены)",
            height=80,
            placeholder="бесплатно\nскачать\nvideo",
            key="minus_input",
        )
        minus_words = []
        if minus_input:
            minus_words = [
                k.strip().lower() for k in minus_input.split("\n") if k.strip()
            ]
            if minus_words:
                st.warning(f"⚠️ Будет исключено: {len(minus_words)} слов")

        filtered_keywords = [
            kw for kw in keywords if not any(mw in kw.lower() for mw in minus_words)
        ]

        if len(filtered_keywords) != len(keywords):
            st.info(f"📉 После фильтрации: {len(filtered_keywords)} из {len(keywords)}")

        if filtered_keywords:
            with st.expander(f"👀 Preview: все ключи ({len(filtered_keywords)})"):
                st.write(", ".join(filtered_keywords[:50]))
                if len(filtered_keywords) > 50:
                    st.caption(f"... и ещё {len(filtered_keywords) - 50}")

    with col2:
        st.markdown("#### Настройки")

        threshold = st.slider(
            "Порог похожести",
            min_value=0.1,
            max_value=0.9,
            value=st.session_state.get("threshold", Config.SIMILARITY_THRESHOLD),
            step=0.05,
            help="Минимальная похожесть SERP для объединения в кластер",
        )

        use_cache = st.checkbox(
            "Использовать кэш SERP",
            value=True,
        )

        st.markdown("---")
        st.markdown("#### API")

        st.text_input(
            "XMLRIVER_USER",
            value=Config.XMLRIVER_USER or "не задан",
            disabled=True,
        )
        st.text_input(
            "XMLRIVER_KEY",
            value="••••••••" if Config.XMLRIVER_KEY else "не задан",
            disabled=True,
        )

    st.divider()

    if st.button(
        "🚀 Запустить кластеризацию", type="primary", use_container_width=True
    ):
        if not filtered_keywords:
            st.error("Нет ключевых слов для кластеризации")
            return

        if not Config.XMLRIVER_USER or not Config.XMLRIVER_KEY:
            st.error("❌ Настройте XMLRIVER_USER и XMLRIVER_KEY в .env")
            return

        with st.spinner(f"Кластеризация {len(filtered_keywords)} ключей..."):
            cache = SERPCache() if use_cache else None
            client = XmlriverClient(cache=cache)

            try:
                clusters = cluster_keywords_func(
                    filtered_keywords, client, threshold=threshold
                )
                st.session_state.clusters = clusters
                st.session_state.unclustered = []
                st.session_state.selected_keywords = set()

                st.success(f"✅ Готово! Сформировано {len(clusters)} кластеров")

            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

    if st.session_state.clusters:
        render_clusters_display(st.session_state.clusters)


def render_clusters_display(clusters: list):
    st.divider()
    st.subheader("📦 Результаты кластеризации")

    if not clusters:
        st.warning("Кластеры не найдены")
        return

    minus_words_list = st.session_state.get("minus_words", [])
    all_sections = (
        [("unclustered", "Не кластеризованные", st.session_state.unclustered)]
        + [("minus_words", "Минус слова", minus_words_list)]
        + [
            (
                f"cluster_{c['id']}",
                c.get("name") or f"Кластер #{c['id']}",
                c["keywords"],
            )
            for c in clusters
        ]
    )
    all_sections = [
        (sid, sname, skwlist) for sid, sname, skwlist in all_sections if skwlist
    ]

    col1, col2, col3 = st.columns(3)
    col1.metric("Всего кластеров", len(clusters))
    col2.metric("Макс. размер", max((len(c["keywords"]) for c in clusters), default=0))
    col3.metric("Не кластеризованные", len(st.session_state.unclustered))

    if clusters:
        st.bar_chart([len(c["keywords"]) for c in clusters])

    search = st.text_input("🔍 Поиск по кластерам", placeholder="введите слово...")

    filtered_sections = all_sections
    if search:
        filtered_sections = [
            (sid, sname, [kw for kw in skwlist if search.lower() in kw.lower()])
            for sid, sname, skwlist in all_sections
            if any(search.lower() in kw.lower() for kw in skwlist)
        ]
        st.caption(f"Найдено секций: {len(filtered_sections)}")

    target_options = ["Не кластеризованные", "Минус слова"] + [
        f"Кластер #{c['id']}" for c in clusters
    ]
    target_idx = st.selectbox(
        "Переместить выбранные в:", target_options, key="move_target"
    )
    target_type = (
        "unclustered"
        if target_idx == "Не кластеризованные"
        else "minus_words"
        if target_idx == "Минус слова"
        else target_idx.replace("Кластер #", "cluster_")
    )

    col_move, col_clear = st.columns([1, 4])
    with col_move:
        if st.button("➡️ Переместить", type="primary", use_container_width=True):
            if not st.session_state.selected_keywords:
                st.warning("Выберите ключевые слова для перемещения")
            else:
                move_keywords = list(st.session_state.selected_keywords)
                current_section = None
                for sid, sname, kwlist in all_sections:
                    if any(kw in kwlist for kw in move_keywords):
                        current_section = sid
                        break

                if current_section == target_type:
                    st.warning("Выберите другое место назначения")
                else:
                    removed = []
                    section_name = "Неизвестно"
                    if current_section:
                        if current_section == "unclustered":
                            removed = [
                                kw
                                for kw in st.session_state.unclustered
                                if kw in move_keywords
                            ]
                            section_name = "Не кластеризованные"
                            st.session_state.unclustered = [
                                kw
                                for kw in st.session_state.unclustered
                                if kw not in move_keywords
                            ]
                        else:
                            cid = int(current_section.replace("cluster_", ""))
                            for c in st.session_state.clusters:
                                if c["id"] == cid:
                                    removed = [
                                        kw
                                        for kw in c["keywords"]
                                        if kw in move_keywords
                                    ]
                                    section_name = f"Кластер #{cid}"
                                    c["keywords"] = [
                                        kw
                                        for kw in c["keywords"]
                                        if kw not in move_keywords
                                    ]
                                    break
                        if removed:
                            st.info(
                                f"🗑️ Удалено из {section_name}: {len(removed)} ключей"
                            )

                    if target_type == "unclustered":
                        st.session_state.unclustered.extend(move_keywords)
                        st.success(
                            f"✅ Перемещено в 'Не кластеризованные': {len(move_keywords)} ключей"
                        )
                    elif target_type == "minus_words":
                        current_minus = st.session_state.get("minus_words", [])
                        st.session_state.minus_words = current_minus + move_keywords
                        st.success(
                            f"✅ Добавлено в минус слова: {len(move_keywords)} ключей"
                        )
                    elif target_type and target_type.startswith("cluster_"):
                        cid = int(target_type.replace("cluster_", ""))
                        for c in st.session_state.clusters:
                            if c["id"] == cid:
                                c["keywords"].extend(move_keywords)
                                st.success(
                                    f"✅ Перемещено в Кластер #{cid}: {len(move_keywords)} ключей"
                                )
                                break

                    st.session_state.selected_keywords = set()
                    st.rerun()

    with col_clear:
        if st.button("Очистить выбор", use_container_width=True):
            st.session_state.selected_keywords = set()
            st.rerun()

    for section_id, section_name, kwlist in filtered_sections:
        section_label = f"📦 {section_name} ({len(kwlist)} ключей)"
        is_unclustered = section_id == "unclustered"
        is_cluster = section_id.startswith("cluster_")

        with st.expander(section_label, expanded=len(kwlist) <= 10):
            for kw in kwlist:
                is_selected = kw in st.session_state.selected_keywords
                col_cb, col_kw = st.columns([1, 20])
                with col_cb:
                    new_val = st.checkbox(
                        "",
                        value=is_selected,
                        key=f"cb_{section_id}_{kw}",
                        label_visibility="collapsed",
                    )
                    if new_val and not is_selected:
                        st.session_state.selected_keywords.add(kw)
                    elif not new_val and is_selected:
                        st.session_state.selected_keywords.discard(kw)
                with col_kw:
                    st.markdown(f"{kw}")

            if is_cluster:
                cid = int(section_id.replace("cluster_", ""))
                cluster_ref = [c for c in st.session_state.clusters if c["id"] == cid]

                if cluster_ref:
                    c = cluster_ref[0]
                    default_name = c.get("name", "") or (
                        c.get("keywords", [""])[0] if c.get("keywords") else ""
                    )

                    st.text_input(
                        "Название",
                        value=default_name,
                        key=f"cluster_name_{cid}",
                        label_visibility="collapsed",
                    )

                    col_del, col_split, _ = st.columns([1, 1, 2])
                    with col_del:
                        if st.button(
                            "🗑️ Удалить",
                            key=f"del_cluster_{cid}",
                            use_container_width=True,
                        ):
                            st.session_state.unclustered.extend(c["keywords"])
                            st.session_state.clusters.remove(c)
                            st.session_state.selected_keywords = set()
                            st.rerun()
                    with col_split:
                        if st.button(
                            "🔄 Расформировать",
                            key=f"split_cluster_{cid}",
                            use_container_width=True,
                        ):
                            st.session_state.unclustered.extend(c["keywords"])
                            st.session_state.clusters.remove(c)
                            st.session_state.selected_keywords = set()
                            st.rerun()
            elif is_unclustered:
                st.caption("Без SERP данных")


def render_data_tab():
    st.subheader("📥 Данные из Яндекс Вебмастера")

    col1, col2 = st.columns(2)

    with col1:
        site_url = st.text_input(
            "Домен сайта",
            value=Config.YANDEX_SITE or "",
            placeholder="https://example.com",
            key="site_url_input",
        )
        st.session_state["site_url"] = site_url

    with col2:
        min_hits = st.number_input(
            "Мин. показов",
            min_value=0,
            value=0,
            key="min_hits_input",
        )
        st.session_state["min_hits"] = min_hits

    col_load, col_clear = st.columns(2)

    with col_load:
        if st.button("📥 Загрузить из WM", type="primary", use_container_width=True):
            if not site_url:
                st.error("Введите домен сайта")
            elif not Config.YANDEX_TOKEN:
                st.error("❌ Настройте YANDEX_OAUTH_TOKEN в .env")
            else:
                with st.spinner("Загружаю данные из Яндекс Вебмастер..."):
                    try:
                        client = YandexWebmasterClient(Config.YANDEX_TOKEN)
                        queries = client.fetch_queries_recent(site_url)

                        if not queries:
                            st.warning("Запросы не найдены")
                        else:
                            saved = client.save_queries_to_db(queries)
                            st.success(f"✅ Сохранено: {saved} записей")

                    except Exception as e:
                        st.error(f"Ошибка: {e}")

    with col_clear:
        if st.button("🗑�� Очистить", use_container_width=True):
            if site_url:
                try:
                    import os

                    db_path = "data/yandex_queries.db"
                    if os.path.exists(db_path):
                        os.remove(db_path)
                        st.success("База очищена")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    st.divider()

    queries = get_wm_queries_from_db(site_url, min_hits)

    if queries:
        st.success(f"📊 В базе: {len(queries)} запросов")

        search = st.text_input("🔍 Поиск по запросам", placeholder="...")

        if search:
            queries = [q for q in queries if search.lower() in q["query"].lower()]
            st.caption(f"Найдено: {len(queries)}")

        for q in queries[:50]:
            st.write(f"- **{q['query']}** ({q['hits']} показов)")

        if len(queries) > 50:
            st.caption(f"... и ещё {len(queries) - 50} запросов")
    else:
        st.info("Нет данных. Нажмите 'Загрузить из WM' для получения запросов.")


def render_settings_tab():
    st.subheader("⚙️ Настройки")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### API Настройки")

        st.text_input(
            "XMLRIVER_USER",
            value=Config.XMLRIVER_USER or "",
            type="default",
            key="xmlriver_user",
        )
        st.text_input(
            "XMLRIVER_KEY",
            value=Config.XMLRIVER_KEY or "",
            type="password",
            key="xmlriver_key",
        )
        st.number_input("Регион", value=Config.XMLRIVER_REGION)
        st.text_input("Поисковая система", value=Config.XMLRIVER_ENGINE)

    with col2:
        st.markdown("#### Yandex WM")

        st.text_input(
            "YANDEX_OAUTH_TOKEN",
            value=Config.YANDEX_TOKEN or "",
            type="password",
            key="yandex_token",
        )
        st.text_input("YANDEX_SITE_URL", value=Config.YANDEX_SITE or "")

    st.divider()

    st.markdown("#### Параметры кластеризации")

    col1, col2, col3 = st.columns(3)

    with col1:
        threshold_new = st.number_input(
            "Порог похожести",
            value=Config.SIMILARITY_THRESHOLD,
            step=0.05,
            key="threshold_setting",
        )

    with col2:
        st.number_input(
            "SERP_TOP_N",
            value=Config.SERP_TOP_N,
            min_value=1,
            max_value=30,
            key="serp_top_n",
        )

    with col3:
        st.number_input(
            "CACHE_TTL_DAYS",
            value=Config.CACHE_TTL_DAYS,
            min_value=1,
            max_value=90,
            key="cache_ttl",
        )

    st.session_state["threshold"] = threshold_new


if __name__ == "__main__":
    main()
