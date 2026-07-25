# nodejs-app/scripts/run_clustering.py
import json
import sys

from utils.bootstrap import bootstrap

bootstrap()

from typing import Any, Callable

from config import Config
from services.cache import SERPCache
from services.clustering import cluster_keywords, merge_serps
from services.serp_collector import prefetch_for_clustering
from services.task_manager import TaskManager
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain


def run_clustering_task(
    domain: str, user_id: int, task_id: int = 0, on_progress: Callable[[str], Any] | None = None
) -> dict:
    domain = extract_domain(domain)
    tm = TaskManager(task_id)
    tm.set_status("running")

    try:
        conn = Config.get_conn()
        cur = conn.cursor(dictionary=True)

        # 1. Get existing clusters
        cur.execute(
            "SELECT query, clustered FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND clustered > 0",
            (user_id, domain),
        )
        rows = cur.fetchall()

        cache = SERPCache()
        client = XmlriverClient(cache=cache)

        existing_groups = {}
        for row in rows:
            cid = row["clustered"]
            kw = row["query"]
            if cid not in existing_groups:
                existing_groups[cid] = []
            existing_groups[cid].append(kw)

        initial_clusters = []
        for cid, kws in existing_groups.items():
            serps = [client.fetch_serp(k, use_cache=True) for k in kws]
            serps = [s for s in serps if s]
            if serps:
                rep = merge_serps(serps)
                initial_clusters.append(
                    {
                        "id": cid,
                        "name": kws[0],
                        "keywords": kws,
                        "serp_representative": rep,
                    }
                )

        # 2. Get unclustered keywords
        cur.execute(
            "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND clustered = 0",
            (user_id, domain),
        )
        unclustered_keywords = [r["query"] for r in cur.fetchall()]

        if not unclustered_keywords:
            tm.set_status("completed")
            return {"success": True, "message": "No new keywords to cluster"}

        tm.update_progress(5)
        if on_progress:
            on_progress("PROGRESS: 5")
        else:
            print("PROGRESS: 5", flush=True)

        # 3. Prefetch SERP for all unclustered keywords (with rate limiting)
        total_kw = len(unclustered_keywords)

        def on_prefetch_progress(done, total):
            prog = 5 + int(done / total * 70)
            tm.update_progress(prog)
            if on_progress:
                on_progress(f"PROGRESS: {prog}")
            else:
                print(f"PROGRESS: {prog}", flush=True)

        prefetch_for_clustering(
            unclustered_keywords,
            client,
            on_progress=on_prefetch_progress,
        )

        # 4. Run incremental clustering (use_cache=True, skip uncached)
        all_clusters = cluster_keywords(
            unclustered_keywords,
            client,
            initial_clusters=initial_clusters,
            skip_cache_miss=True,
        )

        tm.update_progress(85)
        if on_progress:
            on_progress("PROGRESS: 85")
        else:
            print("PROGRESS: 85", flush=True)

        # 5. Update database with results
        update_args = []
        for cluster in all_clusters:
            cluster_id = cluster["id"]
            for kw in cluster["keywords"]:
                update_args.append((cluster_id, user_id, domain, kw))

        if update_args:
            cur.executemany(
                "UPDATE yandex_queries SET clustered = %s WHERE user_id = %s AND site_url = %s AND query = %s",
                update_args,
            )

        conn.commit()

        tm.set_status("completed")
        return {"success": True, "count": len(all_clusters)}

    except Exception as e:
        tm.set_status("failed", str(e))
        import traceback

        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        return {"success": False, "error": error_msg}
    finally:
        if "conn" in locals():
            conn.close()


def run_clustering():
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: run_clustering.py <domain> <user_id> [task_id]",
                }
            )
        )
        return

    domain = extract_domain(sys.argv[1])
    user_id = int(sys.argv[2])
    task_id = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    result = run_clustering_task(domain, user_id, task_id)
    print(json.dumps(result))


if __name__ == "__main__":
    run_clustering()
