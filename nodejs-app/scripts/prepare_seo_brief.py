# scripts/prepare_seo_brief.py
import sys
import os
import json
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv

# Fix console encoding on Windows
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
load_dotenv(os.path.join(project_root, '.env'))

from config import Config

def prepare_brief(domain, cluster_id, user_id):
    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # 1. Get analysis data and raw html
        cur.execute(
            "SELECT analysis_data, raw_html FROM cluster_analysis WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (user_id, domain, cluster_id)
        )
        row = cur.fetchone()
        if not row:
            print(json.dumps({"success": False, "error": "Analysis not found for this cluster"}))
            return
            
        analysis_data = json.loads(row['analysis_data'])
        raw_html = row['raw_html']
        
        # 2. Prepare LLM client
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("BASE_URL")
        )
        model = "gemini-3.1-pro" # As requested by user

        # 3. Step 1: Generate SEO Brief (TOR)
        brief_prompt = f"""
        Вы профессиональный SEO-аналитик. Изучите данные конкурентного анализа и текущей страницы.
        Ваша задача: Составить ТЗ (Техническое задание) на оптимизацию контента страницы под 2026 год.
        
        ЦЕЛЕВОЙ URL: {analysis_data['metadata']['target_url']}
        КЛЮЧЕВЫЕ СЛОВА: {', '.join([k['lemma'] for k in analysis_data['keywords'][:20]])}
        
        ДАННЫЕ КОНКУРЕНТОВ:
        - Медиана слов: {analysis_data['text_metrics']['competitors_median']['words_total']}
        - Рекомендуемые вхождения: {json.dumps(analysis_data['keywords'][:15], ensure_ascii=False)}
        
        ТЕКУЩИЕ МЕТРИКИ СТРАНИЦЫ:
        {json.dumps(analysis_data['text_metrics']['target'], ensure_ascii=False)}
        
        Ответьте на русском языке. ТЗ должно включать:
        1. Рекомендации по объему текста.
        2. Список обязательных LSI-слов и их количество.
        3. Рекомендации по Title, Description и H1-H3.
        4. Структурные правки.
        """
        
        brief_response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": brief_prompt}]
        )
        brief_text = brief_response.choices[0].message.content

        # 4. Step 2: Rewrite content with highlights
        # To avoid sending huge HTML, we might need to extract main content, 
        # but for now let's try sending a chunk or the whole thing if it's small.
        # User wants "visual highlights" in an iframe.
        
        rewrite_prompt = f"""
        Действуй как SEO-копирайтер. На основе следующего ТЗ доработай HTML-код страницы.
        
        ТЗ:
        {brief_text}
        
        ИСХОДНЫЙ HTML (фрагмент или целиком):
        {raw_html[:15000]} # Limit to avoid context window issues
        
        Твоя задача:
        1. Внеси необходимые правки в текст для соответствия ТЗ.
        2. ВСЕ ИЗМЕНЕНИЯ И НОВЫЕ БЛОКИ ТЕКСТА оберни в тег <mark style="background-color: #ffff00; color: black;">...</mark>, чтобы пользователь видел, что было добавлено или изменено.
        3. Верни ТОЛЬКО обновленный HTML-код. Не пиши пояснений.
        """
        
        rewrite_response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": rewrite_prompt}]
        )
        optimized_html = rewrite_response.choices[0].message.content
        
        # Clean up potential markdown formatting from LLM
        if optimized_html.startswith("```html"):
            optimized_html = optimized_html.split("```html")[1].split("```")[0].strip()
        elif optimized_html.startswith("```"):
            optimized_html = optimized_html.split("```")[1].split("```")[0].strip()

        print(json.dumps({
            "success": True,
            "brief": brief_text,
            "optimized_html": optimized_html
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"success": False, "error": "Usage: prepare_seo_brief.py <domain> <cluster_id> <user_id>"}))
    else:
        prepare_brief(sys.argv[1], sys.argv[2], sys.argv[3])
