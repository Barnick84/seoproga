# services/seo_workflow.py
"""Full SEO workflow: Yandex WM -> Clustering -> Page Mapping -> Miratext -> LLM"""

import json
from typing import Dict, List, Optional
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import Config
from services.semantic_core import SemanticCoreManager
from services.page_content_manager import PageContentManager
from services.miratext_client import MiratextClient
from services.seo_agent import SEOAgent
from services.cache import SERPCache
from services.xmlriver_client import XmlriverClient
from services.clustering import cluster_keywords, serp_similarity


SQLITE_DB = "data/seo_workflow.db"


class SEOWorkflow:
    def __init__(self):
        Path("data").mkdir(exist_ok=True)
        self._ensure_tables()

    def _ensure_tables(self):
        if Config.USE_SQLITE:
            conn = sqlite3.connect(SQLITE_DB)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_cluster_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_url TEXT NOT NULL,
                    cluster_id INTEGER NOT NULL,
                    keywords TEXT,
                    status TEXT DEFAULT 'pending',
                    miratext_task_id TEXT,
                    llm_version_id INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    UNIQUE(page_url, cluster_id)
                )
            """)
            conn.commit()
            conn.close()
        else:
            import psycopg2

            dsn = Config.get_pg_dsn()
            create_sql = """
                CREATE TABLE IF NOT EXISTS page_cluster_mapping (
                    id SERIAL PRIMARY KEY,
                    page_url TEXT NOT NULL,
                    cluster_id INTEGER NOT NULL,
                    keywords JSONB,
                    status TEXT DEFAULT 'pending',
                    miratext_task_id TEXT,
                    llm_version_id INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP,
                    UNIQUE(page_url, cluster_id)
                );
            """
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(create_sql)
                conn.commit()

    def get_cluster_keywords(self) -> List[Dict]:
        from services.yandex_webmaster import YandexWebmasterClient
        from services.semantic_core import SemanticCoreManager

        client = YandexWebmasterClient(Config.YANDEX_TOKEN)
        raw_queries = client.fetch_queries_recent(Config.YANDEX_SITE)
        if not raw_queries:
            print("No queries from Yandex Webmaster")
            return []

        saved = client.save_queries_to_db(raw_queries)
        print(f"Saved {saved} queries to DB")

        keywords = client.get_unique_queries_for_clustering(Config.YANDEX_SITE)
        print(f"Unique keywords: {len(keywords)}")

        if not keywords:
            return []

        cache = SERPCache()
        xmlriver_client = XmlriverClient(cache=cache)
        clusters = cluster_keywords(keywords, xmlriver_client)

        manager = SemanticCoreManager()
        db_clusters = []
        for cl in clusters:
            db_clusters.append(
                {
                    "keywords": cl["keywords"],
                    "serp_representative": cl["serp_representative"],
                }
            )
        manager.save_clusters(db_clusters)
        print(f"Created {len(db_clusters)} semantic clusters")

        return clusters

    def map_clusters_to_pages(self, clusters: List[Dict]) -> List[Dict]:
        cache = SERPCache()
        xmlriver_client = XmlriverClient(cache=cache)

        site_url = Config.YANDEX_SITE
        print(f"Fetching pages from {site_url}...")

        try:
            resp = requests.get(site_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            links = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if href.startswith("/") or site_url in href:
                    if href.startswith("/"):
                        full_url = site_url.rstrip("/") + href
                    else:
                        full_url = href
                    if full_url not in links:
                        links.append(full_url)

            links = links[:30]
            print(f"Found {len(links)} pages on site")

        except Exception as e:
            print(f"Error fetching site: {e}")
            links = []

        mappings = []
        for cluster in clusters:
            cluster_keywords_list = cluster["keywords"]
            best_page = None
            best_score = 0.0

            for page_url in links:
                page_serp = xmlriver_client.fetch_serp(page_url)
                if not page_serp:
                    continue

                cluster_serp = cluster.get("serp_representative", [])
                score = serp_similarity(page_serp, cluster_serp)

                if score > best_score:
                    best_score = score
                    best_page = page_url

            if best_page and best_score >= 0.15:
                mappings.append(
                    {
                        "cluster_id": cluster["id"],
                        "keywords": cluster_keywords_list,
                        "page_url": best_page,
                        "score": best_score,
                    }
                )
                self._save_mapping(best_page, cluster["id"], cluster_keywords_list)

        print(f"Mapped {len(mappings)} clusters to pages")
        return mappings

    def _save_mapping(self, page_url: str, cluster_id: int, keywords: List[str]):
        keywords_json = json.dumps(keywords)
        if Config.USE_SQLITE:
            conn = sqlite3.connect(SQLITE_DB)
            conn.execute(
                """
                INSERT OR IGNORE INTO page_cluster_mapping (page_url, cluster_id, keywords, status)
                VALUES (?, ?, ?, 'pending')
            """,
                (page_url, cluster_id, keywords_json),
            )
            conn.commit()
            conn.close()
        else:
            import psycopg2

            with psycopg2.connect(Config.get_pg_dsn()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO page_cluster_mapping (page_url, cluster_id, keywords, status)
                        VALUES (%s, %s, %s, 'pending')
                        ON CONFLICT (page_url, cluster_id) DO NOTHING
                    """,
                        (page_url, cluster_id, keywords_json),
                    )
                conn.commit()

    def run_full_workflow(self):
        print("=" * 50)
        print("Starting FULL SEO workflow")
        print("=" * 50)

        print("\n[1/4] Getting keywords from Yandex Webmaster...")
        clusters = self.get_cluster_keywords()
        if not clusters:
            print("No clusters created")
            return

        print("\n[2/4] Mapping clusters to pages...")
        mappings = self.map_clusters_to_pages(clusters)

        if not mappings:
            print("No page mappings found")
            return

        print("\n[3/4] Fetching and saving page content, analyzing, optimizing...")

        from services.page_content_manager import PageContentManager
        from services.miratext_client import MiratextClient
        from services.seo_agent import SEOAgent

        pm = PageContentManager()
        miratext = MiratextClient()
        agent = SEOAgent()

        processed = 0
        for mapping in mappings:
            page_url = mapping["page_url"]
            keywords = mapping["keywords"]

            try:
                print(f"\nProcessing: {page_url}")

                editable, non_editable = pm.fetch_and_parse_page(page_url)
                pm.save_page(
                    page_url, editable_html=editable, non_editable_html=non_editable
                )
                print(f"   Page saved")

                print(f"   Analyzing with Miratext...")
                miratext_data = miratext.analyze(editable, keywords)

                print(f"   Optimizing with LLM...")
                new_editable = agent.rewrite_page(
                    page_url, editable, keywords, miratext_data
                )

                pm.save_version(page_url, new_editable, keywords)
                full_html = pm.merge_html(new_editable, non_editable)
                pm.save_page(page_url, full_html=full_html, editable_html=new_editable)

                self._update_mapping_status(page_url, mapping["cluster_id"], "saved")
                processed += 1
                print(f"   Done!")

            except Exception as e:
                print(f"   Error: {e}")
                self._update_mapping_status(
                    page_url, mapping["cluster_id"], "failed", str(e)
                )

        print("\n" + "=" * 50)
        print(f"Workflow complete! Processed: {processed}/{len(mappings)}")
        print("=" * 50)

    def _update_mapping_status(
        self,
        page_url: str,
        cluster_id: int,
        status: str,
        error: Optional[str] = None,
    ):
        if Config.USE_SQLITE:
            conn = sqlite3.connect(SQLITE_DB)
            conn.execute(
                """
                UPDATE page_cluster_mapping
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE page_url = ? AND cluster_id = ?
            """,
                (status, error, page_url, cluster_id),
            )
            conn.commit()
            conn.close()
        else:
            import psycopg2

            with psycopg2.connect(Config.get_pg_dsn()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE page_cluster_mapping
                        SET status = %s, error_message = %s, updated_at = NOW()
                        WHERE page_url = %s AND cluster_id = %s
                    """,
                        (status, error, page_url, cluster_id),
                    )
                conn.commit()

    def get_mappings(self) -> List[Dict]:
        if Config.USE_SQLITE:
            conn = sqlite3.connect(SQLITE_DB)
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT id, page_url, cluster_id, keywords, status, error_message
                FROM page_cluster_mapping
                ORDER BY created_at
            """)
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "id": r[0],
                    "page_url": r[1],
                    "cluster_id": r[2],
                    "keywords": r[3],
                    "status": r[4],
                    "error": r[5],
                }
                for r in rows
            ]
        else:
            import psycopg2

            with psycopg2.connect(Config.get_pg_dsn()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, page_url, cluster_id, keywords, status, error_message
                        FROM page_cluster_mapping
                        ORDER BY created_at
                    """)
                    rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "page_url": r[1],
                    "cluster_id": r[2],
                    "keywords": r[3],
                    "status": r[4],
                    "error": r[5],
                }
                for r in rows
            ]
