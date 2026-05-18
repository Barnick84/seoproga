# services/seo_agent.py
from typing import Dict, List, Optional

from openai import OpenAI

from config import Config


SYSTEM_PROMPT = """ Ты senior SEO-копирайтер и фронтенд-разработчик.
Твоя задача: естественно вписать ключевые слова в HTML-текст страницы, строго соблюдая технические рекомендации.
Возвращай ТОЛЬКО готовый HTML. Без markdown-обёрток, без комментариев, без пояснений.
"""

USER_PROMPT_TEMPLATE = """ 📄 СТРАНИЦА: {url}
🔍 ЦЕЛЕВЫЕ КЛЮЧИ: {keywords}
📊 РЕКОМЕНДАЦИИ MIRATEXT:
{miratext_rec}

📝 РЕДАКТИРУЕМАЯ ЧАСТЬ HTML (только <main>/<article>/контент):
```html
{editable_html}
```

⚙️ ТРЕБОВАНИЯ:

1. Впиши каждый ключ ровно `{need_to_add}` раз(а), чтобы итоговое вхождение совпало с `{recommended}`.
2. Сохрани 100% HTML-структуру: теги, атрибуты, классы, ссылки, скрипты, стили.
3. Ключи должны быть грамматически правильными. Разрешены падежи/окончания, если это не меняет морфологию запроса.
4. Не добавляй новых абзацев/блоков без крайней необходимости.
5. Работай ТОЛЬКО с предоставленной редактируемой частью. Не трогай навигацию, футер, шапку.
6. Если ключ уже встречается нужное число раз — оставь как есть.

✅ ОБНОВЛЪННЫЙ HTML (начинай сразу с <html> или с корневого контейнера):
"""


class SEOAgent:
    def __init__(
        self,
        model: Optional[str] = None,
    ):
        self.client = OpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.BASE_URL,
        )
        self.model = model or Config.LLM_MODEL
        self.temperature = Config.LLM_TEMPERATURE
        self.max_tokens = Config.LLM_MAX_TOKENS

    def rewrite_page(
        self,
        url: str,
        editable_html: str,
        keywords: List[str],
        miratext_data: Dict,
    ) -> str:
        prompt = self._build_prompt(url, editable_html, keywords, miratext_data)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        raw_html = response.choices[0].message.content
        if raw_html is None:
            return ""
        return self._clean_llm_output(raw_html.strip())

    def _build_prompt(
        self,
        url: str,
        html: str,
        keywords: List[str],
        rec: Dict,
    ) -> str:
        kw_str = ", ".join(keywords)

        lines = []
        for kw in rec.get("keywords", []):
            lines.append(
                f"- `{kw['keyword']}`: текущих {kw['current']} -> нужно добавить {kw['need_to_add']} (итого: {kw['recommended']})"
            )
        rec_str = "\n".join(lines) if lines else "Нет новых ключей для добавления."

        need_add = sum(kw["need_to_add"] for kw in rec.get("keywords", []))
        recommended = sum(kw["recommended"] for kw in rec.get("keywords", []))

        return USER_PROMPT_TEMPLATE.format(
            url=url,
            keywords=kw_str,
            miratext_rec=rec_str,
            editable_html=html,
            need_to_add=need_add,
            recommended=recommended,
        )

    @staticmethod
    def _clean_llm_output(text: str) -> str:
        text = text.strip()
        if text.startswith("```html"):
            text = text[len("```html") :].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text
    def generate_ideal_structure(self, competitors_headers: List[Dict[str, List[str]]]) -> str:
        """Generate an ideal content structure from competitor headers."""
        context = []
        for i, headers in enumerate(competitors_headers):
            lines = [f"Конкурент {i+1}:"]
            for h_tag, h_list in headers.items():
                for h_text in h_list:
                    lines.append(f"  {h_tag}: {h_text}")
            context.append("\n".join(lines))
        
        headers_context = "\n\n".join(context)
        
        prompt = f"""
На основе заголовков конкурентов ниже, составь идеальную структуру (план) статьи.
Структура должна быть логичной, последовательной и охватывать все важные темы, которые затронули конкуренты.

ПРАВИЛА:
1. Используй только заголовки H2 и H3.
2. Каждый заголовок H2 — это основной раздел.
3. Внутри H2 могут быть подзаголовки H3.
4. Ответ верни в формате JSON:
{{
  "structure": [
    {{
      "tag": "h2",
      "text": "Текст заголовка",
      "items": [
        {{ "tag": "h3", "text": "Текст подзаголовка" }}
      ]
    }}
  ]
}}

ЗАГОЛОВКИ КОНКУРЕНТОВ:
{headers_context}
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Ты эксперт по SEO структурированию контента. Отвечай только валидным JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"}
        )
        
        raw_output = response.choices[0].message.content or ""
        cleaned = raw_output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned
