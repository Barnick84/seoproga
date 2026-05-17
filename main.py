# main.py
import sys
import io
import requests

from config import Config
from services.cache import SERPCache
from services.xmlriver_client import XmlriverClient
from services.clustering import cluster_keywords
from services.yandex_webmaster import YandexWebmasterClient

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main():
    mode = input(
        "Выберите режим:\n"
        "1 - XMLRiver кластеризация\n"
        "2 - Yandex Вебмастер\n"
        "3 - Miratext SEO (ручной режим)\n"
        "4 - Полный SEO цикл\n"
        "> "
    ).strip()

    if mode == "2":
        try:
            Config.validate(mode="yandex")
        except ValueError as e:
            print(f"❌ Ошибка конфигурации: {e}")
            print("💡 Проверьте файл .env")
            return
        main_yandex()
    elif mode == "3":
        try:
            Config.validate(mode="miratext")
        except ValueError as e:
            print(f"❌ Ошибка конфигурации: {e}")
            print("💡 Проверьте .env (MIRATEXT_API_KEY, OPENAI_API_KEY)")
            return
        main_miratext()
    elif mode == "4":
        try:
            Config.validate(mode="yandex")
        except ValueError as e:
            print(f"❌ Ошибка конфигурации: {e}")
            return
        main_full_workflow()
    else:
        try:
            Config.validate(mode="xmlriver")
        except ValueError as e:
            print(f"❌ Ошибка конфигурации: {e}")
            print("💡 Проверьте файл .env")
            return
        main_xmlriver()


def main_yandex():
    print("🚀 Запуск модуля Яндекс.Вебмастер...")

    client = YandexWebmasterClient(Config.YANDEX_TOKEN)

    try:
        raw_queries = client.fetch_queries_recent(Config.YANDEX_SITE)
        if not raw_queries:
            print(
                "⚠️ Запросы не найдены. Проверьте, что сайт добавлен в Вебмастер и прошло >2 дней с индексации."
            )
            return

        saved = client.save_queries_to_db(raw_queries)
        print(f"✅ Сохранено в БД: {saved} записей")

        keywords = client.get_unique_queries_for_clustering(
            Config.YANDEX_SITE, min_hits=5
        )
        print(f"🔑 Уникальных запросов для кластеризации (hits ≥ 5): {len(keywords)}")
        if keywords:
            print("   Примеры:", keywords[:5])
            # Initialize XMLRiver client with cache for SERP fetching
            cache = SERPCache()
            xmlriver_client = XmlriverClient(cache=cache)
            # Process semantic core: create/update clusters in PostgreSQL
            client.process_semantic_core(xmlriver_client)
        print(f"🔑 Уникальных запросов для кластеризации (hits ≥ 5): {len(keywords)}")
        if keywords:
            print("   Примеры:", keywords[:5])

    # Semantic core processing completed; clustering output handled inside process_semantic_core

    except requests.exceptions.HTTPError as e:
        print(f"❌ Ошибка API: {e.response.status_code} → {e.response.text}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def main_xmlriver():
    import json
    import os

    cache = SERPCache()
    client = XmlriverClient(cache=cache)

    test_keywords = [
        "купить iphone 15",
        "iphone 15 цена",
        "айфон 15 характеристики",
        "обзор iphone 15",
        "iphone 15 pro купить",
        "смартфон яблоко",
        "новый айфон 2024",
    ]

    print("🚀 Запускаю кластеризацию...")
    clusters = cluster_keywords(test_keywords, client)

    print(f"\n✅ Готово! Сформировано {len(clusters)} кластеров:\n")
    for cluster in clusters:
        print(f"📦 Кластер #{cluster['id']} ({len(cluster['keywords'])} ключей):")
        for kw in cluster["keywords"]:
            print(f"   • {kw}")
        print()

    os.makedirs("results", exist_ok=True)
    with open("results/clusters.json", "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    print("💾 Результаты сохранены в results/clusters.json")


def main_miratext():
    from services.page_content_manager import PageContentManager
    from services.miratext_client import MiratextClient
    from services.seo_agent import SEOAgent

    print("🚀 Запуск модуля Miratext SEO...")

    pm = PageContentManager()
    miratext = MiratextClient()
    agent = SEOAgent()

    action = input(
        "Выберите действие:\n"
        "1 - Загрузить и сохранить страницу\n"
        "2 - Проанализировать страницу (Miratext)\n"
        "3 - Оптимизировать страницу (LLM)\n"
        "4 - Полный цикл: анализ + оптимизация\n"
        "5 - Показать очередь задач\n"
        "> "
    ).strip()

    if action == "1":
        url = input("Введите URL страницы: ").strip()
        print(f"📥 Загружаю страницу: {url}")
        try:
            editable, non_editable = pm.fetch_and_parse_page(url)
            pm.save_page(url, editable_html=editable, non_editable_html=non_editable)
            print("✅ Страница сохранена в БД")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    elif action == "2":
        url = input("Введите URL страницы: ").strip()
        keywords_input = input("Введите ключевые слова (через запятую): ").strip()
        keywords = [k.strip() for k in keywords_input.split(",")]

        page = pm.get_page(url)
        if not page:
            print("❌ Страница не найдена. Сначала загрузите её (действие 1)")
            return

        editable = page["editable_html"]
        print(f"📊 Анализирую через Miratext ({len(keywords)} ключей)...")
        try:
            result = miratext.analyze(editable, keywords)
            print(f"✅ Анализ завершён. Рекомендаций: {len(result['keywords'])}")
            for kw in result["keywords"]:
                print(
                    f"   {kw['keyword']}: {kw['current']} -> {kw['recommended']} "
                    f"(добавить: {kw['need_to_add']})"
                )
        except Exception as e:
            print(f"❌ Ошибка анализа: {e}")

    elif action == "3":
        url = input("Введите URL страницы: ").strip()
        keywords_input = input("Введите ключевые слова (через запятую): ").strip()
        keywords = [k.strip() for k in keywords_input.split(",")]

        page = pm.get_page(url)
        if not page:
            print("❌ Страница не найдена. Сначала загрузите её (действие 1)")
            return

        editable = page["editable_html"]
        non_editable = page.get("non_editable_html", "")

        miratext_data = {"keywords": []}
        for kw in keywords:
            miratext_data["keywords"].append(
                {"keyword": kw, "current": 0, "recommended": 2, "need_to_add": 2}
            )

        print("🤖 Оптимизирую страницу через LLM...")
        try:
            new_editable = agent.rewrite_page(url, editable, keywords, miratext_data)

            version_id = pm.save_version(url, new_editable, keywords)
            print(f"✅ Версия сохранена (ID: {version_id})")

            full_html = pm.merge_html(new_editable, non_editable)
            pm.save_page(url, full_html=full_html, editable_html=new_editable)
            print("✅ Обновлённая страница сохранена")
        except Exception as e:
            print(f"❌ Ошибка оптимизации: {e}")

    elif action == "4":
        url = input("Введите URL страницы: ").strip()
        keywords_input = input("Введите ключевые слова (через запятую): ").strip()
        keywords = [k.strip() for k in keywords_input.split(",")]

        page = pm.get_page(url)
        if not page:
            print("❌ Страница не найдена. Сначала загрузите её (действие 1)")
            return

        editable = page["editable_html"]
        non_editable = page.get("non_editable_html", "")

        print("📊 Анализирую через Miratext...")
        try:
            miratext_data = miratext.analyze(editable, keywords)
            print(f"   Рекомендаций: {len(miratext_data['keywords'])}")
        except Exception as e:
            print(f"❌ Ошибка Miratext: {e}")
            return

        print("🤖 Оптимизирую страницу через LLM...")
        try:
            new_editable = agent.rewrite_page(url, editable, keywords, miratext_data)

            version_id = pm.save_version(url, new_editable, keywords)
            print(f"   Версия сохранена (ID: {version_id})")

            full_html = pm.merge_html(new_editable, non_editable)
            pm.save_page(url, full_html=full_html, editable_html=new_editable)
            print("✅ Страница оптимизирована и сохранена")
        except Exception as e:
            print(f"❌ Ошибка оптимизации: {e}")

    elif action == "5":
        tasks = pm.get_pending_tasks()
        if not tasks:
            print("📭 Нет задач в очереди")
        else:
            print(f"📋 Задач в очереди: {len(tasks)}")
            for t in tasks:
                print(f"   [{t['id']}] {t['url']} - {t['status']}")

    else:
        print("❌ Неизвестное действие")


def main_full_workflow():
    from services.seo_workflow import SEOWorkflow

    print("🚀 Запуск полного SEO цикла...")

    workflow = SEOWorkflow()
    workflow.run_full_workflow()


if __name__ == "__main__":
    main()
