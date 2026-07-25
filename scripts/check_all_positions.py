import json
import sys
import time
from datetime import datetime

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from services.xmlriver_client import XmlriverClient
from utils.helpers import extract_domain


def check_target(
    client: XmlriverClient,
    query: str,
    engine: str,
    device: str,
    region: int,
    clean_target_domain: str,
) -> tuple[int, str]:
    found_pos = 0
    found_url = ""
    for page in range(10):
        try:
            serp_urls = client.fetch_serp(
                query,
                engine=engine,
                device=device,
                region=region,
                top_n=10,
                page=page,
                use_cache=False,
            )
            if not serp_urls:
                break
            for page_pos, url in enumerate(serp_urls, start=1):
                if clean_target_domain in extract_domain(url):
                    found_pos = page * 10 + page_pos
                    found_url = url
                    break
            if found_pos > 0:
                break
            time.sleep(1)
        except Exception as e:
            print(f"Error {engine}/{device}: {e}", file=sys.stderr)
            break
    return found_pos, found_url


def check_all_positions_task(
    domain: str,
    user_id: int,
    engine: str = "yandex",
    device: str = "desktop",
    on_progress=None,
) -> dict:
    domain = domain.lower().strip()
    clean_target_domain = extract_domain(domain)

    conn = Config.get_conn()
    cur = conn.cursor()

    try:
        user_region = 213
        try:
            cur.execute(
                "SELECT yandex_region_id FROM user_settings WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                user_region = row["yandex_region_id"]
        except Exception:
            pass  # Ignore missing table error

        region_id = 225 if engine == "google" else user_region

        cur.execute(
            """SELECT id, query, clustered AS cluster_id, frequency
               FROM yandex_queries
               WHERE user_id = %s AND site_url = %s AND minus_word = 0
               ORDER BY clustered, query""",
            (user_id, domain),
        )
        keywords = cur.fetchall()

        if not keywords:
            return {
                "success": True,
                "message": "No keywords",
                "checked": 0,
                "total": 0,
            }

        client = XmlriverClient()
        total = len(keywords)
        results = []

        for idx, kw in enumerate(keywords):
            query = kw["query"]
            pct = int(idx / total * 100)
            if on_progress:
                on_progress({"pct": pct, "done": idx, "total": total, "message": query})

            pos, url = check_target(client, query, engine, device, region_id, clean_target_domain)

            results.append(
                {
                    "query": query,
                    "cluster_id": kw["cluster_id"],
                    "position": pos,
                    "frequency": kw.get("frequency") or 0,
                }
            )

            cur.execute(
                """INSERT INTO query_history (user_id, site_url, query, position, found_url, engine, device, region_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, domain, query, pos, url, engine, device, region_id),
            )

            col_map = {
                ("yandex", "desktop"): "hits",
                ("yandex", "mobile"): "hits_ym",
                ("google", "desktop"): "hits_google",
            }
            col = col_map.get((engine, device))
            if col:
                cur.execute(
                    f"UPDATE yandex_queries SET {col} = %s, last_check = %s WHERE id = %s",
                    (pos, datetime.now(), kw["id"]),
                )

            conn.commit()
            time.sleep(0.3)

        if on_progress:
            on_progress({"pct": 100, "done": total, "total": total, "message": "Готово!"})

        return {"success": True, "checked": len(results), "total": total}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: check_all_positions.py <domain> <user_id> [engine] [device]",
                }
            )
        )
        return

    domain = sys.argv[1]
    user_id = int(sys.argv[2])
    engine = sys.argv[3] if len(sys.argv) > 3 else "yandex"
    device = sys.argv[4] if len(sys.argv) > 4 else "desktop"

    def on_progress(msg: str):
        print(msg)
        sys.stdout.flush()

    result = check_all_positions_task(domain, user_id, engine, device, on_progress)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
