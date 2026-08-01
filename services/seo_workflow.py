# services/seo_workflow.py
"""Full SEO workflow: Yandex WM -> Clustering -> Page Mapping -> Miratext -> LLM"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from config import Config
from services.cache import SERPCache
from services.clustering import cluster_keywords, serp_similarity
from services.miratext_client import MiratextClient
from services.page_content_manager import PageContentManager
from services.semantic_core import SemanticCoreManager
from services.seo_agent import SEOAgent
from services.xmlriver_client import XmlriverClient
from utils.db import get_db_cursor

logger = logging.getLogger(__name__)

SQLITE_DB = "data/seo_workflow.db"


def _placeholder() -> str:
    return "?" if Config.DB_TYPE == "sqlite" else "%s"


@contextmanager
def _get_cursor(commit: bool = False):
    if Config.DB_TYPE == "sqlite":
        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
    else:
        with get_db_cursor(dictionary=True, commit=commit) as (_conn, cur):
            yield cur


class SEOWorkflow:
    def __init__(self):
        Path("data").mkdir(exist_ok=True)
        self._ensure_tables()

    def _ensure_tables(self):
        if Config.DB_TYPE == "sqlite":
            ddl = """
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
            """
        elif Config.DB_TYPE == "postgresql":
            ddl = """
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
        else:
            ddl = """
                CREATE TABLE IF NOT EXISTS page_cluster_mapping (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    page_url VARCHAR(2048) NOT NULL,
                    cluster_id INT NOT NULL,
                    keywords JSON,
                    status VARCHAR(32) DEFAULT 'pending',
                    miratext_task_id VARCHAR(128),
                    llm_version_id INT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    UNIQUE KEY uq_page_cluster (page_url(255), cluster_id)
                )
            """
        with _get_cursor(commit=True) as cur:
            cur.execute(ddl)

    def get_cluster_keywords(self, user_id: int) -> List[Dict]:
        from services.yandex_webmaster import YandexWebmasterClient

        client = YandexWebmasterClient(Config.YANDEX_TOKEN, user_id=user_id)
        raw_queries = client.fetch_queries_recent(Config.YANDEX_SITE)
        if not raw_queries:
            logger.info("No queries from Yandex Webmaster")
            return []

        saved = client.save_queries_to_db(raw_queries)
        logger.info("Saved %s queries to DB", saved)

        keywords = client.get_unique_queries_for_clustering(Config.YANDEX_SITE)
        logger.info("Unique keywords: %s", len(keywords))

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
        manager.save_clusters(db_clusters, user_id=user_id, site_url=Config.YANDEX_SITE)
        logger.info("Created %s semantic clusters", len(db_clusters))

        return clusters

    def _fetch_site_links(self, site_url: str) -> List[str]:
        try:
            resp = requests.get(site_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            links = []
            for a in soup.find_all("a", href=True):
                href = str(a.get("href", ""))
                if href.startswith("/") or site_url in href:
                    if href.startswith("/"):
                        full_url = site_url.rstrip("/") + href
                    else:
                        full_url = href
                    if full_url not in links:
                        links.append(full_url)

            links = links[:30]
            logger.info("Found %s pages on site", len(links))
            return links
        except Exception as e:
            logger.warning("Error fetching site: %s", e)
            return []

    def map_clusters_to_pages(self, clusters: List[Dict]) -> List[Dict]:
        cache = SERPCache()
        xmlriver_client = XmlriverClient(cache=cache)

        site_url = Config.YANDEX_SITE
        logger.info("Fetching pages from %s...", site_url)

        links = self._fetch_site_links(site_url)

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

        return mappings

    def _save_mapping(self, page_url: str, cluster_id: int, keywords: List[str]) -> None:
        keywords_json = json.dumps(keywords)
        ph = _placeholder()
        if Config.DB_TYPE == "sqlite":
            sql = (
                "INSERT OR IGNORE INTO page_cluster_mapping (page_url, cluster_id, keywords, status) "
                f"VALUES ({ph}, {ph}, {ph}, 'pending')"
            )
        elif Config.DB_TYPE == "postgresql":
            sql = (
                "INSERT INTO page_cluster_mapping (page_url, cluster_id, keywords, status) "
                f"VALUES ({ph}, {ph}, {ph}, 'pending') "
                "ON CONFLICT (page_url, cluster_id) DO NOTHING"
            )
        else:
            sql = (
                "INSERT IGNORE INTO page_cluster_mapping (page_url, cluster_id, keywords, status) "
                f"VALUES ({ph}, {ph}, {ph}, 'pending')"
            )
        with _get_cursor(commit=True) as cur:
            cur.execute(sql, (page_url, cluster_id, keywords_json))

    def _process_mapping(
        self, mapping: Dict, pm: PageContentManager, miratext: MiratextClient, agent: SEOAgent
    ) -> bool:
        page_url = mapping["page_url"]
        keywords = mapping["keywords"]

        try:
            logger.info("Processing: %s", page_url)

            editable, non_editable = pm.fetch_and_parse_page(page_url)
            pm.save_page(page_url, editable_html=editable, non_editable_html=non_editable)
            logger.info("   Page saved")

            logger.info("   Analyzing with Miratext...")
            miratext_data = miratext.analyze(editable, keywords)

            logger.info("   Optimizing with LLM...")
            new_editable = agent.rewrite_page(page_url, editable, keywords, miratext_data)

            pm.save_version(page_url, new_editable, keywords)
            full_html = pm.merge_html(new_editable, non_editable)
            pm.save_page(page_url, full_html=full_html, editable_html=new_editable)

            self._update_mapping_status(page_url, mapping["cluster_id"], "saved")
            logger.info("   Done!")
            return True

        except Exception as e:
            logger.warning("   Error: %s", e)
            self._update_mapping_status(page_url, mapping["cluster_id"], "failed", str(e))
            return False

    def run_full_workflow(self, user_id: int):
        logger.info("Starting FULL SEO workflow")

        logger.info("[1/4] Getting keywords from Yandex Webmaster...")
        clusters = self.get_cluster_keywords(user_id=user_id)
        if not clusters:
            logger.info("No clusters created")
            return

        logger.info("[2/4] Mapping clusters to pages...")
        mappings = self.map_clusters_to_pages(clusters)

        if not mappings:
            logger.info("No page mappings found")
            return

        logger.info("[3/4] Fetching and saving page content, analyzing, optimizing...")

        pm = PageContentManager()
        miratext = MiratextClient()
        agent = SEOAgent()

        processed = 0
        for mapping in mappings:
            if self._process_mapping(mapping, pm, miratext, agent):
                processed += 1

        logger.info("Workflow complete! Processed: %s/%s", processed, len(mappings))

    def _update_mapping_status(
        self,
        page_url: str,
        cluster_id: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        ph = _placeholder()
        with _get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE page_cluster_mapping "
                f"SET status = {ph}, error_message = {ph}, updated_at = CURRENT_TIMESTAMP "
                f"WHERE page_url = {ph} AND cluster_id = {ph}",
                (status, error, page_url, cluster_id),
            )

    def get_mappings(self) -> List[Dict]:
        with _get_cursor() as cur:
            cur.execute(
                """
                SELECT id, page_url, cluster_id, keywords, status, error_message
                FROM page_cluster_mapping
                ORDER BY created_at
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "page_url": r["page_url"],
                "cluster_id": r["cluster_id"],
                "keywords": r["keywords"],
                "status": r["status"],
                "error": r["error_message"],
            }
            for r in rows
        ]
