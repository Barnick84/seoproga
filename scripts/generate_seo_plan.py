# scripts/generate_seo_plan.py
import json
import os
import sys
from datetime import datetime

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

# Fix console encoding on Windows
from utils.bootstrap import bootstrap

bootstrap()
load_dotenv(".env")

from urllib.parse import urlparse

from utils.db import get_db_cursor


def get_target_url(cur, user_id, domain, cluster_id):
    # Normalize domain to Cyrillic
    domain = domain.lower().strip()
    if domain.startswith("xn--"):
        try:
            domain = domain.encode("ascii").decode("idna")
        except UnicodeError as e:
            print(f"IDNA decode error for {domain}: {e}", file=sys.stderr)

    cur.execute(
        "SELECT target_url FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
        (user_id, domain, cluster_id),
    )
    row = cur.fetchone()
    if row and row.get("target_url"):
        url = row["target_url"]
        if not url.startswith("http"):
            base = domain if domain.startswith("http") else "https://" + domain
            url = base.rstrip("/") + "/" + url.lstrip("/")
        return url
    return None


def generate_seo_plan(domain, cluster_id, user_id, rewrite_content=False):
    try:
        # Normalize domain to Cyrillic
        domain = domain.lower().strip()
        if domain.startswith("xn--"):
            try:
                domain = domain.encode("ascii").decode("idna")
            except UnicodeError as e:
                print(f"IDNA decode error for {domain}: {e}", file=sys.stderr)

        with get_db_cursor(commit=False) as (conn, cur):
            # 1. Get analysis data and raw html
            cur.execute(
                "SELECT analysis_data, raw_html FROM cluster_analysis WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (user_id, domain, cluster_id),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "success": False,
                    "error": "Анализ не найден для данного кластера. Сначала запустите общий СЕО анализ.",
                }

            # Handle string or dict
            analysis_data = row["analysis_data"]
            if isinstance(analysis_data, str):
                analysis_data = json.loads(analysis_data)

            raw_html = row["raw_html"] or ""
            intent_type = analysis_data.get("intent", {}).get("target", "Информационный")

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("BASE_URL"))
            model = os.getenv("LLM_MODEL", "gemini-3.1-pro")

            prompt_text = ""

            if intent_type == "Коммерческий":
                soup = BeautifulSoup(raw_html, "html.parser")

                # Helper to find robust tag containing substantial text
                def find_robust_tag(s):
                    art = s.find("article")
                    if art and len(art.get_text(strip=True)) > 20:
                        return art
                    mn = s.find("main")
                    if mn and len(mn.get_text(strip=True)) > 20:
                        return mn
                    return s.find("article") or s.find("main")

                target_tag = find_robust_tag(soup)

                # If not found in cached HTML or empty, try live fetch
                if not target_tag or len(target_tag.get_text(strip=True)) <= 20:
                    target_url = get_target_url(cur, user_id, domain, cluster_id)
                    if target_url:
                        try:
                            import requests

                            fetch_url = target_url
                            try:
                                parsed = urlparse(target_url)
                                if parsed.netloc:
                                    puny_netloc = parsed.netloc.encode("idna").decode("ascii")
                                    fetch_url = target_url.replace(parsed.netloc, puny_netloc)
                            except UnicodeError as e:
                                print(f"IDNA encode error for {target_url}: {e}", file=sys.stderr)

                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                            }
                            resp = requests.get(fetch_url, headers=headers, timeout=15)
                            if resp.status_code == 200:
                                live_html = resp.text
                                live_soup = BeautifulSoup(live_html, "html.parser")
                                live_target = find_robust_tag(live_soup)
                                if live_target:
                                    raw_html = live_html
                                    soup = live_soup
                                    target_tag = live_target
                                    # Update DB cache with fresh HTML
                                    cur.execute(
                                        "UPDATE cluster_analysis SET raw_html = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                                        (raw_html, user_id, domain, cluster_id),
                                    )
                                    conn.commit()
                        except requests.RequestException as e:
                            print(f"Live HTML fetch failed for {target_url}: {e}", file=sys.stderr)
                        except Exception as e:
                            print(
                                f"Unexpected error during live HTML fetch for {target_url}: {e}",
                                file=sys.stderr,
                            )

                if not target_tag or (
                    not rewrite_content and len(target_tag.get_text(strip=True)) <= 20
                ):
                    error_msg = (
                        "### ⚠️ Отсутствует семантическая разметка\n\n"
                        "**Что такое семантическая разметка?**\n\n"
                        "Семантическая разметка — это использование специальных HTML5-тегов (таких как `<main>` или `<article>`) "
                        "вместо обычных несемантических блоков (`<div>`), чтобы явно указать поисковым роботам и браузерам смысловую роль каждого элемента на странице.\n\n"
                        "**Для чего она нужна и как влияет на SEO-продвижение?**\n\n"
                        "1. **Изоляция полезного контента**: Поисковые роботы Яндекса и Google используют эти теги для отделения уникального содержимого страницы от повторяющихся сквозных блоков (шапка сайта, меню, сайдбар, футер). Это защищает ваш продвигаемый текст от «размытия» нерелевантными ключевыми словами из меню и подвала.\n"
                        "2. **Концентрация веса**: Обернув ключевой текст в `<main>` или `<article>`, вы даете поисковикам прямой сигнал: *«Именно эта часть страницы отвечает на поисковый запрос пользователя. Анализируйте её в первую очередь»*.\n"
                        "3. **Повышение качества индексации**: Правильная структура разметки повышает шансы попадания страницы в топ и формирования более привлекательных, релевантных сниппетов в поисковой выдаче.\n\n"
                        "**Инструкция по исправлению:**\n\n"
                        "В шаблоне страницы или коде вашего сайта найдите область основного контента (описание услуги, статью, уникальный текст) и оберните её в тег `<main>` или `<article>`. \n"
                        "Убедитесь, что все сквозные блоки (шапка `<header>`, подвал `<footer>`, меню `<nav>`, боковая колонка `<aside>`) находятся *вне* этого тега.\n\n"
                        "**Пример правильного структурирования страницы:**\n"
                        "```html\n"
                        "<header>\n"
                        "    <!-- Логотип, меню, контакты -->\n"
                        "</header>\n\n"
                        "<main>\n"
                        "    <h1>Заголовок услуги / Статьи</h1>\n"
                        "    <p>Основной продвигаемый текст и уникальный контент страницы...</p>\n"
                        "</main>\n\n"
                        "<footer>\n"
                        "    <!-- Ссылка на политику, контакты, копирайт -->\n"
                        "</footer>\n"
                        "```"
                    )
                    return {"success": False, "error": error_msg}

                target_content = str(target_tag)
                start_idx = raw_html.find(target_content)

                if start_idx != -1:
                    html_before = raw_html[:start_idx]
                    html_after = raw_html[start_idx + len(target_content) :]
                else:
                    html_before = "Не удалось извлечь предшествующий HTML."
                    html_after = "Не удалось извлечь последующий HTML."

                # Limit sizes to prevent context window bloat
                html_before = html_before[-5000:]  # Only need immediate preceding context
                html_after = html_after[:5000]  # Only need immediate succeeding context
                target_content = target_content[:10000]

                words_in_target_tag = (
                    len(target_tag.get_text(strip=True).split()) if target_tag else 0
                )
                char_no_spaces_in_target_tag = (
                    len("".join(target_tag.get_text(strip=True).split())) if target_tag else 0
                )

                action_text = (
                    "ПОЛНОЕ ПЕРЕПИСЫВАНИЕ: Напишите ТЗ для полного переписывания контента в целевом теге с нуля."
                    if rewrite_content
                    else "ДО-ОПТИМИЗАЦИЯ: Напишите ТЗ для до-оптимизации текущего текста в целевом теге с сохранением смысла и дописыванием нужных ключей/LSI."
                )
            else:
                words_in_target_tag = 0
                char_no_spaces_in_target_tag = 0
                action_text = ""

            # 2. Fetch LSI keywords from DB
            cur.execute(
                "SELECT keyword, frequency FROM cluster_lsi WHERE user_id = %s AND site_url = %s AND cluster_id = %s ORDER BY frequency DESC",
                (user_id, domain, cluster_id),
            )
            lsi_rows = cur.fetchall()
            lsi_list = [f"{row['keyword']} (частота: {row['frequency']})" for row in lsi_rows]
            lsi_text = ", ".join(lsi_list) if lsi_list else "LSI ключи не найдены в базе данных."

            # 3. Extract text metrics
            text_metrics = analysis_data.get("text_metrics", {})
            target_metrics = text_metrics.get("target", {})
            median_metrics = text_metrics.get("competitors_median", {})

            target_words = target_metrics.get("words_total", 0)
            median_words = median_metrics.get("words_total", 0)

            target_chars = target_metrics.get("characters_without_spaces", 0)
            median_chars = median_metrics.get("characters_without_spaces", 0)

            target_water = target_metrics.get("wateriness", 0)
            median_water = median_metrics.get("wateriness", 0)

            target_stuffing = target_metrics.get("stuffing", 0)
            median_stuffing = median_metrics.get("stuffing", 0)

            target_zipf = target_metrics.get("zipf", 0)
            median_zipf = median_metrics.get("zipf", 0)

            # 4. Extract keywords, bigrams, trigrams safely
            raw_keywords = analysis_data.get("keywords", [])
            if isinstance(raw_keywords, list):
                if raw_keywords and isinstance(raw_keywords[0], dict):
                    keywords_text = ", ".join(
                        [k.get("query", k.get("keyword", "")) for k in raw_keywords if k]
                    )
                else:
                    keywords_text = ", ".join([str(k) for k in raw_keywords if k])
            else:
                keywords_text = str(raw_keywords)

            raw_bigrams = analysis_data.get("bigrams", [])
            if isinstance(raw_bigrams, list):
                if raw_bigrams and isinstance(raw_bigrams[0], dict):
                    bigrams_text = ", ".join(
                        [f"{b.get('phrase', '')} ({b.get('count', '')})" for b in raw_bigrams if b]
                    )
                else:
                    bigrams_text = ", ".join([str(b) for b in raw_bigrams if b])
            else:
                bigrams_text = str(raw_bigrams)

            raw_trigrams = analysis_data.get("trigrams", [])
            if isinstance(raw_trigrams, list):
                if raw_trigrams and isinstance(raw_trigrams[0], dict):
                    trigrams_text = ", ".join(
                        [f"{t.get('phrase', '')} ({t.get('count', '')})" for t in raw_trigrams if t]
                    )
                else:
                    trigrams_text = ", ".join([str(t) for t in raw_trigrams if t])
            else:
                trigrams_text = str(raw_trigrams)

            # 5. Compile structure (saved user structure vs competitor headers)
            saved_structure = analysis_data.get("saved_structure", {}).get("data", [])
            if saved_structure:
                structure_source = "ПОЛЬЗОВАТЕЛЬСКАЯ СТРУКТУРА СТАТЬИ (Используйте её строго!):\n"
                for i, item in enumerate(saved_structure, 1):
                    level = item.get("level", "H2")
                    title_text = item.get("title", "")
                    desc = item.get("description", "")
                    structure_source += f"{i}. [{level}] {title_text}\n"
                    if desc:
                        structure_source += f"   Описание: {desc}\n"
            else:
                structure_source = "СТРУКТУРА ЗАГОЛОВКОВ НА САЙТАХ КОНКУРЕНТОВ:\n"
                comp_details = analysis_data.get("competitors_details", [])
                has_headers = False
                for comp in comp_details:
                    c_meta = comp.get("meta", {})
                    c_url = comp.get("url", "")
                    c_headers = c_meta.get("headers", {})
                    if c_headers:
                        has_headers = True
                        structure_source += f"\nКонкурент ({c_url}):\n"
                        for h_tag in ["h1", "h2", "h3", "h4"]:
                            if h_tag in c_headers and c_headers[h_tag]:
                                structure_source += (
                                    f"  {h_tag.upper()}: {', '.join(c_headers[h_tag])}\n"
                                )
                if not has_headers:
                    structure_source += "Заголовки конкурентов не найдены в анализе. Спроектируйте структуру самостоятельно."

            # 6. Generate the Copywriting ТЗ prompt
            prompt_text = f"""
            Вы профессиональный контент-стратег и SEO-специалист высокого уровня.
            Ваша задача — составить подробное, исчерпывающее ТЗ (Техническое задание) для копирайтера на создание или оптимизацию контента.

            КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
            - Создавать или выводить финальный готовый пример текста или статьи!
            - Писать фрагменты готового текста для вставки!
            Ваш ответ должен быть исключительно Техническим заданием (ТЗ) для написания текста копирайтером.

            КОНТЕКСТ СТРАНИЦЫ И ДАННЫЕ АНАЛИЗА:
            - Интент страницы: {intent_type}
            - URL страницы: {get_target_url(cur, user_id, domain, cluster_id) or f"https://{domain}"}
            - Title страницы: {analysis_data.get("target_meta", {}).get("title", "Не найден")}
            
            ТЕКУЩЕЕ СОСТОЯНИЕ КОНТЕНТА:
            - Общее кол-во слов на странице: {target_words}
            - Кол-во слов в изменяемой части (в целевом теге): {words_in_target_tag} (всего символов без пробелов: {char_no_spaces_in_target_tag})
            
            МЕДИАННЫЕ ПОКАЗАТЕЛИ ТОП-10 КОНКУРЕНТОВ:
            - Общее кол-во слов: {median_words}
            - Символов без пробелов: {median_chars}
            - Водянистость: {median_water}%
            - Тошнота (stuffing): {median_stuffing}%
            - Оценка по Закону Ципфа: {median_zipf}
            
            ОСНОВНЫЕ КЛЮЧЕВЫЕ ЗАПРОСЫ (КЛАСТЕР):
            {keywords_text}
            
            ПОПУЛЯРНЫЕ БИГРАМЫ И ТРИГРАМЫ КОНКУРЕНТОВ (для разбавления ключей):
            - Биграмы: {bigrams_text}
            - Триграмы: {trigrams_text}
            
            LSI-КЛЮЧЕВЫЕ СЛОВА (СОБРАННЫЕ В АНАЛИЗЕ):
            {lsi_text}
            
            СЕРП / СТРУКТУРА ЗАГОЛОВКОВ:
            {structure_source}

            ПРАВИЛА И ТРЕБОВАНИЯ К ТЗ, КОТОРЫЕ ВЫ ДОЛЖНЫ СФОРМУЛИРОВАТЬ И ПРОПИСАТЬ В СВОЕМ ОТВЕТЕ:
            
            1. **Роль автора (E-E-A-T)**:
               - Проанализируйте Title страницы ("{analysis_data.get("target_meta", {}).get("title", "Не найден")}") и определите конкретную экспертную роль автора, от лица которого должен писаться текст (например, "опытный юрист по банкротству", "практикующий гид по Кавказу", "сертифицированный визовый специалист"). Пропишите в ТЗ, в каком тоне, стиле (Tone of Voice) и с каким позиционированием должен писать автор.
            
            2. **Объем текста**:
               - Укажите точный рекомендуемый диапазон объема текста для написания копирайтером (в словах и символах без пробелов) для встраивания в целевую область страницы с учетом того, что на странице уже есть неизменяемый контент (шапка, меню, футер и т.д.). Объем должен позволить приблизиться к медиане ТОП-10 конкурентов ({median_words} слов).
            
            3. **Правила вписывания ключевых слов и разбавления**:
               - Составьте четкие требования по интеграции основных ключевых запросов:
                 - Сколько раз каждый запрос должен встретиться в чистом виде (точное вхождение).
                 - Как и чем разбавлять эти ключевые слова на основе популярных биграмм и триграмм конкурентов. Приведите конкретные примеры допустимых словоформ и разбавлений для копирайтера (например, как основной запрос можно разбавить другими словами, основываясь на биграммах/триграммах).
            
            4. **Интеграция LSI ключевых слов**:
               - Перечислите LSI ключевые слова и пропишите инструкции по их естественному и равномерному распределению по тексту.
            
            5. **SEO-параметры контента**:
               - Водянистость: установите жесткий лимит (например, не более {median_water + 2}%, ориентируясь на медиану {median_water}%).
               - Тошнота (академическая и классическая плотность): установите лимит плотности вхождений ключевых слов на основе медианы конкурентов ({median_stuffing}%).
               - Закон Ципфа: пропишите правило для копирайтера по соблюдению естественной частотности слов (избегать искусственного перенасыщения, сохранять логарифмический спад частоты употребления слов от наиболее частых к редким).
            
            6. **Идеальная структура (план статьи)**:
               - На основе предоставленной структуры (пользовательской или конкурентов) составьте и опишите идеальный, логичный план будущей статьи/текста с разметкой заголовков (H1, H2, H3). Для каждого раздела кратко укажите, о чем там писать и какие именно ключи/LSI туда логичнее всего встроить.
            
            {f"РЕЖИМ НАПИСАНИЯ: {action_text}" if intent_type == "Коммерческий" else ""}

            Сформируйте ТЗ на русском языке в профессиональном, структурированном и понятном для копирайтера формате Markdown.
            """

            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt_text}]
            )
            plan_content = response.choices[0].message.content

            # Save to DB
            today_date = datetime.now().strftime("%Y-%m-%d")

            upsert_query = """
                INSERT INTO cluster_seo_history 
                (user_id, site_url, cluster_id, analysis_date, intent_type, seo_plan_content)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                intent_type = VALUES(intent_type), 
                seo_plan_content = VALUES(seo_plan_content)
            """
            cur.execute(
                upsert_query,
                (user_id, domain, cluster_id, today_date, intent_type, plan_content),
            )
            conn.commit()

        return {
            "success": True,
            "date": today_date,
            "intent": intent_type,
            "plan": plan_content,
        }

    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stderr)
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: generate_seo_plan.py <domain> <cluster_id> <user_id>",
                }
            )
        )
    else:
        rewrite = True if len(sys.argv) >= 5 and sys.argv[4] == "1" else False
        result = generate_seo_plan(sys.argv[1], sys.argv[2], sys.argv[3], rewrite)
        print(json.dumps(result, ensure_ascii=False))
