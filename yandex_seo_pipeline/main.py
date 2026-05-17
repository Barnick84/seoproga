# yandex_seo_pipeline/main.py
import argparse
import sys
import json
from core.pipeline import YandexSEOPipeline
from core.data_models import PageInput
from core.logger import logger
import os
from dotenv import load_dotenv

# Load environment variables from .env in the parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    parser = argparse.ArgumentParser(description="Yandex SEO Pipeline 2026")
    parser.add_argument("--url", type=str, required=True, help="Target URL")
    parser.add_argument("--cluster", type=str, required=True, help="Comma-separated cluster keywords")
    parser.add_argument("--config", type=str, help="Path to config.yaml")
    
    args = parser.parse_args()
    
    # Default config path logic
    config_path = args.config
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    
    keywords = [k.strip() for k in args.cluster.split(",")]
    
    input_data = PageInput(
        url=args.url,
        cluster=keywords,
        lsi=["купить", "доставка"], # Mock LSI
        top10_html=["<html><body><h2>Header</h2></body></html>"], # Mock top10
        region="213"
    )
    
    pipeline = YandexSEOPipeline(config_path=config_path)
    output = pipeline.run(input_data)
    
    if output.status == "success":
        logger.info("cli_run_success")
        with open("output_article.html", "w", encoding="utf-8") as f:
            f.write(output.optimized_html)
        print("Pipeline finished successfully. Output saved to output_article.html")
    else:
        logger.error("cli_run_error", status=output.status)
        print(f"Pipeline failed: {output.status}")
        sys.exit(1)

if __name__ == "__main__":
    main()
