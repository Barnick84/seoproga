import sys
import os
import json
import requests
from urllib.parse import urlparse

if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config
from services.custom_analyzer import CustomAnalyzer
from utils.helpers import extract_domain


def load_stop_urls() -> set:
    """Load stop domains from stop_url.md in project root."""
    stop_path = os.path.join(project_root, "stop_url.md")
    domains = set()
    if os.path.exists(stop_path):
        with open(stop_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    domains.add(line)
    domains.update(d.lower() for d in Config.EXCLUDED_DOMAINS)
    return domains


def get_target_url(conn, user_id: int, domain: str, cluster_id: int) -> str | None:
    """Fetch target URL from cluster_mappings."""
    domain_cyr = domain.lower().strip()
    if domain_cyr.startswith("xn--"):
        try:
            domain_cyr = domain_cyr.encode("ascii").decode("idna")
        except:
            pass

    cur = conn.cursor()
    cur.execute(
        "SELECT target_url FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
        (user_id, domain_cyr, cluster_id)
    )
    row = cur.fetchone()
    if row and row.get("target_url"):
        url = row["target_url"]
        if not url.startswith("http"):
            base = domain if domain.startswith("http") else "https://" + domain
            url = base.rstrip("/") + "/" + url.lstrip("/")
        return url
    return None


def find_relevant_page(domain: str, main_keyword: str) -> str | None:
    """Try to find a relevant page via XMLRiver SERP filtered by the promoted domain."""
    try:
        from services.xmlriver_client import XmlriverClient
        client = XmlriverClient()
        urls = client.fetch_serp(main_keyword, top_n=20)
        base_domain = extract_domain("https://" + domain if not domain.startswith("http") else domain)
        for url in urls:
            if base_domain and base_domain in url:
                return url
    except Exception as e:
        print(f"[WARN] find_relevant_page failed: {e}", file=sys.stderr)
    return None


def get_cluster_keywords(conn, user_id: int, domain: str, cluster_id: int) -> list:
    """Get keywords sorted by frequency desc."""
    domain_cyr = domain.lower().strip()
    if domain_cyr.startswith("xn--"):
        try:
            domain_cyr = domain_cyr.encode("ascii").decode("idna")
        except:
            pass

    cur = conn.cursor()
    cur.execute(
        "SELECT query, COALESCE(frequency, 0) as frequency "
        "FROM yandex_queries "
        "WHERE user_id = %s AND site_url = %s AND clustered = %s AND minus_word = 0 "
        "ORDER BY frequency DESC, hits DESC",
        (user_id, domain_cyr, cluster_id)
    )
    return cur.fetchall()


def fetch_competitors_with_stop_filter(
    main_keyword: str, stop_domains: set, promoted_domain: str, min_count: int = 6
) -> list[str]:
    """Fetch TOP-10 from XMLRiver, filter stop_url, get page 2 if needed."""
    from services.xmlriver_client import XmlriverClient
    client = XmlriverClient()

    promoted_base = extract_domain(
        "https://" + promoted_domain if not promoted_domain.startswith("http") else promoted_domain
    )

    def filter_urls(urls: list) -> list:
        result = []
        for url in urls:
            d = extract_domain(url)
            if not d:
                continue
            if d in stop_domains:
                continue
            if promoted_base and promoted_base in d:
                continue
            if url not in result:
                result.append(url)
        return result

    urls_p1 = client.fetch_serp(main_keyword, top_n=10, page=0)
    filtered = filter_urls(urls_p1)

    if len(filtered) < min_count:
        urls_p2 = client.fetch_serp(main_keyword, top_n=10, page=1)
        filtered_p2 = filter_urls(urls_p2)
        existing = set(filtered)
        for u in filtered_p2:
            if u not in existing:
                filtered.append(u)
                existing.add(u)

    return filtered[:10]


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: run_seo_analysis.py <domain> <cluster_id> [user_id]"}))
        return

    domain = sys.argv[1].lower().strip()
    if domain.startswith("xn--"):
        try:
            domain = domain.encode("ascii").decode("idna")
        except Exception:
            pass

    cluster_id = int(sys.argv[2])
    user_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    conn = None
    try:
        conn = Config.get_mysql_conn()

        keywords_rows = get_cluster_keywords(conn, user_id, domain, cluster_id)
        if not keywords_rows:
            print(json.dumps({"success": False, "error": "Нет ключевых слов в кластере"}))
            return

        keywords = [row["query"] for row in keywords_rows]
        main_keyword = keywords[0]

        target_url = get_target_url(conn, user_id, domain, cluster_id)

        if not target_url:
            target_url = find_relevant_page(domain, main_keyword)

        if not target_url:
            print(json.dumps({
                "success": False,
                "no_target": True,
                "error": "Релевантная страница не найдена. Укажите существующую релевантную ключевому запросу страницу сайта. Если её нет, создайте и укажите URL созданной страницы."
            }))
            return

        stop_domains = load_stop_urls()
        comp_urls = fetch_competitors_with_stop_filter(main_keyword, stop_domains, domain)

        print(f"[INFO] Main keyword: {main_keyword}", file=sys.stderr)
        print(f"[INFO] Target URL: {target_url}", file=sys.stderr)
        print(f"[INFO] Competitors found: {len(comp_urls)}", file=sys.stderr)

        analyzer = CustomAnalyzer()
        analyzer.excluded_domains = stop_domains

        target_html = None
        try:
            fetch_url = target_url
            try:
                parsed = urlparse(target_url)
                if parsed.netloc:
                    puny_netloc = parsed.netloc.encode('idna').decode('ascii')
                    fetch_url = target_url.replace(parsed.netloc, puny_netloc)
            except Exception:
                pass
            resp = requests.get(
                fetch_url, timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            resp.raise_for_status()
            target_html = resp.text
        except Exception as e:
            print(f"[WARN] Could not fetch target page: {e}", file=sys.stderr)

        analysis = analyzer.process_analysis(
            target_url=target_url,
            keywords=keywords,
            raw_html=target_html,
            competitor_urls=comp_urls
        )

        analysis["cluster_id"] = cluster_id
        analysis["main_keyword"] = main_keyword

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cluster_analysis (user_id, site_url, cluster_id, analysis_data, raw_html) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE analysis_data = VALUES(analysis_data), raw_html = VALUES(raw_html)",
            (
                user_id,
                domain,
                cluster_id,
                json.dumps(analysis, ensure_ascii=False),
                target_html or ""
            )
        )

        print(json.dumps({"success": True, "message": f"SEO анализ завершён для {main_keyword}"}))

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
