# yandex_seo_pipeline/core/pipeline.py
from typing import Dict, Any, List
from core.data_models import PageInput, PipelineOutput
from core.logger import logger
import yaml

from modules.intent_classifier import IntentClassifier
from modules.meta_optimizer import MetaOptimizer
from modules.blueprint_gen import BlueprintGenerator
from modules.content_generator import ContentGenerator
from modules.tech_auditor import TechAuditor
from modules.exporter import Exporter

class YandexSEOPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        logger.info("initializing_pipeline", config=config_path)
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            logger.warning("config_load_failed", error=str(e), fallback="using_defaults")
            self.config = {}

        self.intent_classifier = IntentClassifier()
        self.meta_optimizer = MetaOptimizer()
        self.blueprint_gen = BlueprintGenerator()
        self.content_gen = ContentGenerator()
        self.tech_auditor = TechAuditor(self.config)
        self.exporter = Exporter()

    def run(self, input_data: PageInput) -> PipelineOutput:
        logger.info("pipeline_started", url=input_data.url)
        logs = []
        try:
            # 1. Intent Classification
            intent_res = self.intent_classifier.classify(input_data.cluster[0])
            logs.append(f"Intent classified as {intent_res.intent} ({intent_res.confidence})")

            # 2. Meta Optimization
            target_title = "Моя страница - Заголовок" # Mock target
            target_desc = "Описание страницы" # Mock target
            comp_titles = ["Конкурент 1", "Конкурент 2"] # Mock comp
            comp_descs = ["Описание 1", "Описание 2"] # Mock comp
            
            meta_res = self.meta_optimizer.optimize(
                target_title, target_desc, comp_titles, comp_descs
            )
            logs.append(f"Meta optimized. Missing words added.")

            # 3. Blueprint Generation
            blueprint = self.blueprint_gen.generate(
                input_data.top10_html, input_data.cluster, input_data.lsi
            )
            logs.append(f"Blueprint generated with {len(blueprint.outline)} sections.")

            # 4. Content Generation
            raw_html = self.content_gen.generate(blueprint)
            logs.append(f"Content generated via LLM.")

            # 5. Tech Audit
            audit_res = self.tech_auditor.audit(input_data.url, raw_html)
            if not audit_res.passed:
                logs.append(f"Tech audit found issues: {len(audit_res.issues)}")
            else:
                logs.append("Tech audit passed.")

            # 6. Export and Assembly
            final_html, json_ld = self.exporter.assemble(input_data.url, raw_html, meta_res, blueprint)
            logs.append("Final HTML assembled.")

            output = PipelineOutput(
                optimized_html=final_html,
                meta_title=meta_res.optimized_example["title"],
                meta_desc=meta_res.optimized_example["description"],
                json_ld=json_ld,
                audit_report=audit_res,
                status="success",
                logs=logs
            )
            logger.info("pipeline_completed_successfully")
            return output

        except Exception as e:
            logger.error("pipeline_failed", error=str(e))
            return PipelineOutput(
                optimized_html="",
                meta_title="",
                meta_desc="",
                json_ld="",
                audit_report=None,
                status=f"error: {str(e)}",
                logs=logs + [f"FAILED: {str(e)}"]
            )
