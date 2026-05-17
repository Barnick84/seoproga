# yandex_seo_pipeline/modules/blueprint_gen.py
from typing import List, Dict, Any
from core.data_models import ArticleBlueprint
from core.logger import logger
from bs4 import BeautifulSoup
import re

class BlueprintGenerator:
    def __init__(self):
        pass

    def _extract_headers(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        headers = []
        for tag in soup.find_all(['h2', 'h3']):
            text = tag.get_text(separator=" ").strip()
            if len(text) > 5:
                headers.append(text)
        return headers

    def generate(self, comp_htmls: List[str], keywords: List[str], lsi: List[str]) -> ArticleBlueprint:
        logger.info("generating_blueprint", competitors=len(comp_htmls))
        
        all_headers = []
        word_counts = []
        
        for html in comp_htmls:
            all_headers.extend(self._extract_headers(html))
            # simple word count
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ")
            words = re.findall(r'\b\w+\b', text)
            word_counts.append(len(words))
            
        median_words = sorted(word_counts)[len(word_counts)//2] if word_counts else 1000
        
        # Dummy generation of outline based on top headers (very basic)
        outline = [
            {"type": "h2", "title": "Введение"},
        ]
        
        if all_headers:
            # take 3 random/first headers
            for h in list(set(all_headers))[:3]:
                 outline.append({"type": "h2", "title": h})
                 
        outline.append({"type": "h2", "title": "FAQ"})
        outline.append({"type": "h2", "title": "Заключение эксперта"})

        blueprint = ArticleBlueprint(
            outline=outline,
            median_total_words=median_words,
            required_ngrams=["n-gram1", "n-gram2"], # Placeholder
            keywords=keywords,
            lsi=lsi
        )
        
        logger.info("blueprint_generated", outline_size=len(outline), median_words=median_words)
        return blueprint
