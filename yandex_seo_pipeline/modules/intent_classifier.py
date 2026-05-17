# yandex_seo_pipeline/modules/intent_classifier.py
from typing import List, Optional
from core.data_models import IntentResult
from core.logger import logger
import re

class IntentClassifierError(Exception):
    pass

class IntentClassifier:
    def __init__(self):
        self.commercial_markers = ["купить", "цена", "заказать", "стоимость", "интернет-магазин"]
        self.informational_markers = ["как", "что", "почему", "отзывы", "обзор", "инструкция"]
        
    def classify(self, query: str, top10_urls: Optional[List[str]] = None) -> IntentResult:
        logger.info("classifying_intent", query=query)
        try:
            q_lower = query.lower()
            
            # Very basic lexical classification
            commercial_score = sum(1 for marker in self.commercial_markers if marker in q_lower)
            informational_score = sum(1 for marker in self.informational_markers if marker in q_lower)
            
            intent = "mixed"
            confidence = 0.5
            recommendation = "Balance commercial and informational content."
            
            if commercial_score > informational_score:
                intent = "commercial"
                confidence = 0.8
                recommendation = "Focus on product blocks, pricing, and CTA."
            elif informational_score > commercial_score:
                intent = "informational"
                confidence = 0.8
                recommendation = "Focus on detailed guides, FAQs, and expert insights."
                
            result = IntentResult(
                intent=intent,
                confidence=confidence,
                recommendation=recommendation
            )
            logger.info("intent_classified", intent=result.intent, confidence=result.confidence)
            return result
            
        except Exception as e:
            logger.error("intent_classification_failed", error=str(e))
            raise IntentClassifierError(f"Failed to classify intent: {str(e)}")
