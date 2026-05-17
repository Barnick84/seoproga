# yandex_seo_pipeline/modules/meta_optimizer.py
from typing import List, Dict
from core.data_models import MetaOptimizationReport
from core.logger import logger
import re
from collections import Counter

class MetaOptimizer:
    def __init__(self):
        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            logger.warning("pymorphy3 not found, falling back to basic lemmatization")
            self.morph = None

        self.title_limit = 60
        self.desc_limit = 155

    def _lemmatize(self, text: str) -> List[str]:
        words = re.findall(r'[а-яА-ЯёЁa-zA-Z]+', text.lower())
        lemmas = []
        for word in words:
            if len(word) < 3:
                continue
            if self.morph:
                p = self.morph.parse(word)[0]
                lemmas.append(p.normal_form)
            else:
                lemmas.append(word)
        return lemmas

    def optimize(self, target_title: str, target_desc: str, comp_titles: List[str], comp_descs: List[str]) -> MetaOptimizationReport:
        logger.info("optimizing_meta", target_title=target_title)
        
        # Analyze competitor titles
        all_comp_lemmas = []
        for t in comp_titles:
            all_comp_lemmas.extend(set(self._lemmatize(t))) # Unique per document
            
        counts = Counter(all_comp_lemmas)
        
        # Words appearing in >30% of top 10
        min_docs = max(1, len(comp_titles) * 0.3)
        popular_lemmas = [lemma for lemma, count in counts.items() if count >= min_docs]
        
        target_lemmas = set(self._lemmatize(target_title))
        missing_words = [w for w in popular_lemmas if w not in target_lemmas]
        
        # Generate simple optimized example by appending missing words (in reality, LLM should do this)
        opt_title = target_title
        if missing_words:
            append_str = " ".join(missing_words[:2])
            if len(opt_title) + len(append_str) + 3 <= self.title_limit:
                opt_title = f"{opt_title} - {append_str}"
                
        space_left = {
            "title": self.title_limit - len(opt_title),
            "description": self.desc_limit - len(target_desc)
        }
        
        report = MetaOptimizationReport(
            current={"title": target_title, "description": target_desc},
            missing_words=missing_words,
            optimized_example={"title": opt_title, "description": target_desc},
            space_left=space_left
        )
        
        logger.info("meta_optimized", missing_words=len(missing_words))
        return report
