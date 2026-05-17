# scripts/run_custom_analysis.py
import sys
import sqlite3
import json
import os
from datetime import datetime

# Add root directory to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.custom_analyzer import CustomAnalyzer
from config import Config

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Domain required"}))
        return

    domain = sys.argv[1]
    cluster_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    db_path = 'data/yandex_queries.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    analyzer = CustomAnalyzer()

    # Get clusters to analyze
    if cluster_id:
        cur.execute(
            "SELECT cluster_id, target_url FROM cluster_mappings WHERE site_url = ? AND cluster_id = ?",
            (domain, cluster_id)
        )
    else:
        cur.execute(
            "SELECT cluster_id, target_url FROM cluster_mappings WHERE site_url = ?",
            (domain,)
        )
    
    mappings = cur.fetchall()
    
    if not mappings:
        print(json.dumps({"success": False, "error": "No mappings found for domain"}))
        conn.close()
        return

    results_count = 0
    for cid, target_url in mappings:
        # Get keywords for this cluster
        cur.execute(
            "SELECT query FROM yandex_queries WHERE site_url = ? AND clustered = ?",
            (domain, cid)
        )
        keywords = [row[0] for row in cur.fetchall()]
        
        if not keywords:
            continue

        try:
            # Run analysis
            analysis_result = analyzer.process_analysis(target_url, keywords)
            
            # Save to DB
            cur.execute(
                """
                INSERT OR REPLACE INTO cluster_analysis (site_url, cluster_id, analysis_data, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (domain, cid, json.dumps(analysis_result, ensure_ascii=False), datetime.now().isoformat())
            )
            conn.commit()
            results_count += 1
            
            # Print progress for streaming
            print(json.dumps({"progress": f"Analyzed cluster {cid}", "cluster_id": cid}))
            sys.stdout.flush()
            
        except Exception as e:
            print(json.dumps({"error": f"Failed analyzing cluster {cid}: {str(e)}"}))
            sys.stdout.flush()

    conn.close()
    print(json.dumps({"success": True, "analyzed": results_count}))

if __name__ == "__main__":
    main()
