# nodejs-app/scripts/run_mapping.py
import json
import sys
from urllib.parse import urlparse

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.cache import SERPCache
from services.clustering import merge_serps
from services.task_manager import TaskManager
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain


def get_domain_from_url(url):
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    return extract_domain(netloc)


def run_mapping_task(
    domain: str, user_id: int, single_cluster_id: int | None = None, task_id: int = 0
) -> dict:
    domain = extract_domain(domain)
    tm = TaskManager(task_id)
    tm.set_status("running")

    try:
        conn = Config.get_conn()
        cur = conn.cursor()

        # 1. Get cluster IDs
        if single_cluster_id:
            cur.execute(
                "SELECT DISTINCT clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
                (user_id, domain, single_cluster_id),
            )
        else:
            cur.execute(
                "SELECT DISTINCT clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered > 0",
                (user_id, domain),
            )
        cluster_ids = [r["clustered"] for r in cur.fetchall()]

        if not cluster_ids:
            result = {"success": True, "message": "No clusters to map"}
            tm.set_result(result)
            tm.set_status("completed")
            return result

        tm.update_progress(10)

        # 2. Network operations
        cache = SERPCache()
        client = XmlriverClient(cache=cache)
        mappings = {}
        total = len(cluster_ids)
        processed = 0

        for cid in cluster_ids:
            processed += 1
            progress_val = 10 + int((processed / total) * 80)
            tm.update_progress(progress_val)
            print(f"PROGRESS: {progress_val}", flush=True)

            cur.execute(
                "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
                (user_id, domain, cid),
            )
            keywords = [r["query"] for r in cur.fetchall()]

            if not keywords:
                mappings[cid] = None
                continue

            serps = [client.fetch_serp(k, use_cache=True) for k in keywords]
            serps = [s for s in serps if s]

            if not serps:
                mappings[cid] = None
                continue

            merged_urls = merge_serps(serps)

            best_url = None
            for url in merged_urls:
                if get_domain_from_url(url) == domain:
                    best_url = url
                    break

            if best_url:
                temp_url = best_url if best_url.startswith("http") else "http://" + best_url
                parsed = urlparse(temp_url)
                rel_path = parsed.path
                if parsed.query:
                    rel_path += "?" + parsed.query
                mappings[cid] = rel_path
            else:
                mappings[cid] = None

        # 3. Save results
        for cid, target_url in mappings.items():
            cur.execute(
                "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE target_url = VALUES(target_url)",
                (user_id, domain, cid, target_url),
            )

        conn.commit()
        result = {"success": True, "count": len(mappings)}
        tm.set_result(result)
        tm.set_status("completed")
        return result

    except Exception as e:
        tm.set_status("failed", str(e))
        return {"success": False, "error": str(e)}
    finally:
        if "conn" in locals():
            conn.close()


def run_mapping():
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: run_mapping.py <domain> <user_id> [cluster_id] [task_id]",
                }
            )
        )
        return

    domain = extract_domain(sys.argv[1])
    user_id = int(sys.argv[2])
    single_cluster_id = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "None" else None
    task_id = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    result = run_mapping_task(domain, user_id, single_cluster_id, task_id)
    print(json.dumps(result))


if __name__ == "__main__":
    run_mapping()
