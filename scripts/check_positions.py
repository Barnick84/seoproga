# nodejs-app/scripts/check_positions.py
import json
import sys
import time
from datetime import datetime

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain
from utils.position_checker import check_target


def check_positions_task(
    domain: str,
    cluster_id: int,
    user_id: int = 0,
    cmd_region: str | None = None,
    on_progress=None,
) -> dict:
    domain = domain.lower().strip()
    if domain.startswith("xn--"):
        try:
            domain = domain.encode("ascii").decode("idna")
        except Exception:
            pass
    clean_target_domain = extract_domain(domain)

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        # 0. Get user region
        if cmd_region and cmd_region.isdigit():
            user_region = int(cmd_region)
        else:
            cur.execute(
                "SELECT yandex_region_id FROM user_settings WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            user_region = row["yandex_region_id"] if row else 213

        # 1. Get keywords
        cur.execute(
            "SELECT id, query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s",
            (user_id, domain, cluster_id),
        )
        keywords = cur.fetchall()

        if not keywords:
            return {
                "success": True,
                "message": "No keywords in cluster",
                "positions": [],
            }

        client = XmlriverClient()
        results = []

        for idx, kw in enumerate(keywords, start=1):
            query = kw["query"]
            kw_id = kw["id"]

            if on_progress:
                on_progress(
                    {
                        "status": "progress",
                        "current": idx,
                        "total": len(keywords),
                        "message": f"Checking {query}...",
                    }
                )

            # Check Yandex Desktop
            if on_progress:
                on_progress(
                    {
                        "status": "progress",
                        "current": idx,
                        "total": len(keywords),
                        "message": "> Yandex Desktop...",
                    }
                )
            pos_yd, url_yd = check_target(
                client, query, "yandex", "desktop", user_region, clean_target_domain
            )

            # Check Yandex Mobile
            if on_progress:
                on_progress(
                    {
                        "status": "progress",
                        "current": idx,
                        "total": len(keywords),
                        "message": "> Yandex Mobile...",
                    }
                )
            pos_ym, url_ym = check_target(
                client, query, "yandex", "mobile", user_region, clean_target_domain
            )

            # Check Google Desktop (Region Russia = 225)
            if on_progress:
                on_progress(
                    {
                        "status": "progress",
                        "current": idx,
                        "total": len(keywords),
                        "message": "> Google Desktop...",
                    }
                )
            pos_g, url_g = check_target(
                client, query, "google", "desktop", 225, clean_target_domain
            )

            results.append(
                {
                    "query": query,
                    "pos_yd": pos_yd,
                    "pos_ym": pos_ym,
                    "pos_g": pos_g,
                    "url_yd": url_yd,
                    "url_ym": url_ym,
                    "url_g": url_g,
                }
            )

            # Save to history
            targets = [
                ("yandex", "desktop", pos_yd, url_yd, user_region),
                ("yandex", "mobile", pos_ym, url_ym, user_region),
                ("google", "desktop", pos_g, url_g, 225),
            ]
            for engine, device, pos, url, reg in targets:
                cur.execute(
                    """INSERT INTO query_history (user_id, site_url, query, position, found_url, engine, device, region_id) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, domain, query, pos, url, engine, device, reg),
                )

            # Update main query table
            cur.execute(
                """UPDATE yandex_queries 
                   SET hits = %s, hits_ym = %s, hits_google = %s, last_check = %s 
                   WHERE id = %s""",
                (pos_yd, pos_ym, pos_g, datetime.now(), kw_id),
            )

            time.sleep(0.5)

        conn.commit()
        return {
            "success": True,
            "message": f"Checked {len(results)} keywords on 3 engines",
            "positions": results,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def main():
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: check_positions.py <domain> <cluster_id> [user_id]",
                }
            )
        )
        return

    domain = sys.argv[1]
    cluster_id = int(sys.argv[2])
    user_id = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cmd_region = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None

    def on_progress(msg: str):
        print(f"PROGRESS: {msg}")
        sys.stdout.flush()

    result = check_positions_task(domain, cluster_id, user_id, cmd_region, on_progress)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
