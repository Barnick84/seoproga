# yandex_seo_pipeline/modules/content_generator.py
import os
from openai import OpenAI
from core.data_models import ArticleBlueprint
from core.logger import logger

class ContentGeneratorError(Exception):
    pass

class ContentGenerator:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not found. LLM generation will fail.")
            
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def generate(self, blueprint: ArticleBlueprint) -> str:
        logger.info("generating_content", model=self.model, outline_size=len(blueprint.outline))
        try:
            prompt = f"Напиши SEO-статью на {blueprint.median_total_words} слов.\n"
            prompt += f"Ключевые слова: {', '.join(blueprint.keywords)}\n"
            prompt += f"LSI: {', '.join(blueprint.lsi)}\n"
            prompt += "Структура:\n"
            for item in blueprint.outline:
                prompt += f"- {item['type'].upper()}: {item['title']}\n"
                
            prompt += "\nИспользуй E-E-A-T стандарты, пиши экспертно, верни чистый HTML без markdown."

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты Senior SEO Copywriter & Expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content
            logger.info("content_generated", length=len(content))
            return content
            
        except Exception as e:
            logger.error("content_generation_failed", error=str(e))
            raise ContentGeneratorError(f"LLM generation failed: {str(e)}")
