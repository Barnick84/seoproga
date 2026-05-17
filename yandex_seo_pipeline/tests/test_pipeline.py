# yandex_seo_pipeline/tests/test_pipeline.py
import pytest
from ..core.data_models import PageInput
from ..modules.intent_classifier import IntentClassifier
from ..modules.tech_auditor import TechAuditor

def test_page_input_model():
    input_data = PageInput(
        url="https://test.com",
        cluster=["test keyword"]
    )
    assert input_data.url == "https://test.com"
    assert input_data.region == "213"
    assert len(input_data.cluster) == 1

def test_intent_classifier():
    classifier = IntentClassifier()
    res_comm = classifier.classify("купить телефон")
    assert res_comm.intent == "commercial"
    
    res_info = classifier.classify("как выбрать телефон")
    assert res_info.intent == "informational"

def test_tech_auditor():
    auditor = TechAuditor()
    res = auditor.audit("https://test.com", "<html><body>No JSON-LD here</body></html>")
    assert res.passed == False
    assert len(res.issues) > 0
