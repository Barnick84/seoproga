# yandex_seo_pipeline/core/data_models.py
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class PageInput(BaseModel):
    url: str
    cluster: List[str]
    lsi: List[str] = Field(default_factory=list)
    top10_html: List[str] = Field(default_factory=list)
    region: str = "213"

class IntentResult(BaseModel):
    intent: str  # commercial | informational | transactional | mixed
    confidence: float
    recommendation: str

class MetaOptimizationReport(BaseModel):
    current: Dict[str, str]  # title, description
    missing_words: List[str]
    optimized_example: Dict[str, str]
    space_left: Dict[str, int]

class ArticleBlueprint(BaseModel):
    outline: List[Dict[str, Any]]
    median_total_words: int
    required_ngrams: List[str]
    keywords: List[str]
    lsi: List[str]

class Issue(BaseModel):
    priority: str
    message: str

class TechAuditReport(BaseModel):
    cwv_scores: Dict[str, float]
    issues: List[Issue]
    passed: bool

class PipelineOutput(BaseModel):
    optimized_html: str
    meta_title: str
    meta_desc: str
    json_ld: str
    audit_report: Optional[TechAuditReport] = None
    status: str
    logs: List[str]
