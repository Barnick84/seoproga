# yandex_seo_pipeline/modules/exporter.py
from core.data_models import ArticleBlueprint, MetaOptimizationReport
from core.logger import logger
import json
from datetime import datetime

class Exporter:
    def __init__(self):
        pass

    def generate_json_ld(self, url: str, meta: MetaOptimizationReport) -> str:
        ld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": meta.optimized_example["title"],
            "description": meta.optimized_example["description"],
            "url": url,
            "datePublished": datetime.now().isoformat(),
            "author": {
                "@type": "Person",
                "name": "Expert Author"
            }
        }
        return json.dumps(ld, ensure_ascii=False)

    def assemble(self, url: str, html_body: str, meta: MetaOptimizationReport, blueprint: ArticleBlueprint) -> str:
        logger.info("assembling_final_html", url=url)
        
        json_ld = self.generate_json_ld(url, meta)
        
        full_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{meta.optimized_example["title"]}</title>
    <meta name="description" content="{meta.optimized_example["description"]}">
    <link rel="canonical" href="{url}">
    <script type="application/ld+json">
{json_ld}
    </script>
</head>
<body>
    <article>
{html_body}
    </article>
</body>
</html>"""
        
        return full_html, json_ld
