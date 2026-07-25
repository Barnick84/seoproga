import sys
import os
import json

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.seo_agent import SEOAgent


def generate_structure_task(domain: str, user_id: int, cluster_id: int, keywords: list[str]) -> dict:
    try:
        conn = Config.get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT analysis_data FROM cluster_analysis WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (user_id, domain, cluster_id),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Анализ не найден для данного кластера."}
        
        analysis_data = row["analysis_data"]
        if isinstance(analysis_data, str):
            analysis_data = json.loads(analysis_data)
            
        comp_details = analysis_data.get("competitors_details", [])
        competitors_headers = []
        for comp in comp_details:
            c_meta = comp.get("meta", {})
            c_headers = c_meta.get("headers", {})
            if c_headers:
                competitors_headers.append(c_headers)
                
        agent = SEOAgent()
        result_json = agent.generate_ideal_structure(competitors_headers)
        
        return {"success": True, "structure": json.loads(result_json)}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if 'conn' in locals() and conn:
            conn.close()


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"success": False, "error": "Usage: generate_structure.py <domain> <user_id> <cluster_id> <keywords_json>"}))
        return

    domain = sys.argv[1].strip()
    user_id = int(sys.argv[2])
    cluster_id = int(sys.argv[3])
    try:
        keywords = json.loads(sys.argv[4])
    except Exception:
        keywords = []

    result = generate_structure_task(domain, user_id, cluster_id, keywords)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
