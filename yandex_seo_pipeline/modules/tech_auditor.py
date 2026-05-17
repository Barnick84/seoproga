# yandex_seo_pipeline/modules/tech_auditor.py
from typing import Dict, Any
from core.data_models import TechAuditReport, Issue
from core.logger import logger
import json

class TechAuditor:
    def __init__(self, config: dict = None):
        self.config = config or {}
        # Ensure default cwv values if not present in config
        if "pipeline" in self.config and "cwv" in self.config["pipeline"]:
             self.cwv_config = self.config["pipeline"]["cwv"]
        else:
             self.cwv_config = {"inp_max": 200, "lcp_max": 2.5, "cls_max": 0.1}

    def _mock_lighthouse_run(self, url: str) -> Dict[str, float]:
        # In a real scenario, this would call subprocess 'lighthouse' or PageSpeed Insights API
        logger.debug("running_mock_lighthouse", url=url)
        return {
            "inp": 150.0,
            "lcp": 1.8,
            "cls": 0.05
        }

    def audit(self, url: str, html: str) -> TechAuditReport:
        logger.info("running_tech_audit", url=url)
        
        cwv_scores = self._mock_lighthouse_run(url)
        issues = []
        passed = True
        
        cfg = self.cwv_config
        if cwv_scores["inp"] > cfg["inp_max"]:
            issues.append(Issue(priority="high", message=f"INP too high: {cwv_scores['inp']}ms"))
            passed = False
        if cwv_scores["lcp"] > cfg["lcp_max"]:
            issues.append(Issue(priority="high", message=f"LCP too high: {cwv_scores['lcp']}s"))
            passed = False
        if cwv_scores["cls"] > cfg["cls_max"]:
            issues.append(Issue(priority="high", message=f"CLS too high: {cwv_scores['cls']}"))
            passed = False
            
        # Basic JSON-LD validation
        if 'application/ld+json' not in html:
            issues.append(Issue(priority="medium", message="No JSON-LD found in HTML"))
            passed = False
            
        report = TechAuditReport(
            cwv_scores=cwv_scores,
            issues=issues,
            passed=passed
        )
        
        logger.info("tech_audit_completed", passed=passed, issues_count=len(issues))
        return report
