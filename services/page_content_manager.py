# services/page_content_manager.py
from typing import Dict, List, Optional, Tuple

import psycopg2
from bs4 import BeautifulSoup

from config import Config


NON_EDITABLE_SELECTORS = [
    "nav",
    "header",
    "footer",
    "aside",
    ".header",
    ".footer",
    ".sidebar",
    "#header",
    "#footer",
    "#sidebar",
    ".nav",
    ".menu",
    ".navigation",
    "script",
    "style",
]

EDITABLE_SELECTORS = [
    "main",
    "article",
    "[role='main']",
    ".content",
    ".main-content",
    "#content",
    "#main",
]


class PageContentManager:
    def __init__(self):
        self.dsn = Config.get_pg_dsn()
        self._ensure_tables()

    def _ensure_tables(self):
        create_pages_table = """
            CREATE TABLE IF NOT EXISTS page_content (
                id SERIAL PRIMARY KEY,
                page_url TEXT UNIQUE NOT NULL,
                full_html TEXT,
                editable_html TEXT NOT NULL,
                non_editable_html TEXT,
                last_fetched TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (page_url)
            );
        """
        create_versions_table = """
            CREATE TABLE IF NOT EXISTS page_versions (
                id SERIAL PRIMARY KEY,
                page_url TEXT NOT NULL,
                editable_html TEXT NOT NULL,
                keywords JSONB,
                miratext_task_id TEXT,
                llm_model_used TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (page_url) REFERENCES page_content(page_url) ON DELETE CASCADE
            );
        """
        create_tasks_table = """
            CREATE TABLE IF NOT EXISTS seo_tasks (
                id SERIAL PRIMARY KEY,
                page_url TEXT NOT NULL,
                cluster_id INTEGER,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'analyzing', 'analyzed', 'rewriting', 'rewritten', 'saved', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                FOREIGN KEY (page_url) REFERENCES page_content(page_url) ON DELETE CASCADE
            );
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(create_pages_table)
                cur.execute(create_versions_table)
                cur.execute(create_tasks_table)
            conn.commit()

    def fetch_and_parse_page(self, url: str) -> Tuple[str, str]:
        import requests

        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
        return self.split_editable_content(html)

    def split_editable_content(self, html: str) -> Tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")

        editable_parts = []

        for selector in EDITABLE_SELECTORS:
            elements = soup.select(selector)
            for elem in elements:
                editable_parts.append(str(elem))
                elem.decompose()

        if editable_parts:
            editable_html = "\n".join(editable_parts)
        else:
            body = soup.find("body")
            if body:
                editable_html = str(body)
            else:
                editable_html = html

        non_editable_html = str(soup)

        return editable_html, non_editable_html

    def save_page(
        self,
        url: str,
        full_html: Optional[str] = None,
        editable_html: Optional[str] = None,
        non_editable_html: Optional[str] = None,
    ) -> bool:
        if full_html and not editable_html:
            editable_html, non_editable_html = self.split_editable_content(full_html)

        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO page_content (page_url, full_html, editable_html, non_editable_html, last_fetched)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (page_url) DO UPDATE SET
                        full_html = EXCLUDED.full_html,
                        editable_html = EXCLUDED.editable_html,
                        non_editable_html = EXCLUDED.non_editable_html,
                        last_fetched = NOW()
                    """,
                    (url, full_html, editable_html, non_editable_html),
                )
            conn.commit()
        return True

    def get_page(self, url: str) -> Optional[Dict]:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT page_url, full_html, editable_html, non_editable_html, last_fetched FROM page_content WHERE page_url = %s",
                    (url,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "url": row[0],
            "full_html": row[1],
            "editable_html": row[2],
            "non_editable_html": row[3],
            "last_fetched": row[4],
        }

    def save_version(
        self,
        url: str,
        editable_html: str,
        keywords: List[str],
        miratext_task_id: Optional[str] = None,
    ) -> int:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO page_versions (page_url, editable_html, keywords, miratext_task_id, llm_model_used)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (url, editable_html, keywords, miratext_task_id, Config.LLM_MODEL),
                )
                result = cur.fetchone()
                version_id = result[0] if result else 0
            conn.commit()
        return version_id

    def get_latest_version(self, url: str) -> Optional[Dict]:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, page_url, editable_html, keywords, miratext_task_id, llm_model_used, created_at
                    FROM page_versions
                    WHERE page_url = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (url,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "url": row[1],
            "editable_html": row[2],
            "keywords": row[3],
            "miratext_task_id": row[4],
            "llm_model": row[5],
            "created_at": row[6],
        }

    def create_task(
        self,
        url: str,
        cluster_id: Optional[int] = None,
    ) -> int:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO seo_tasks (page_url, cluster_id, status) VALUES (%s, %s, 'pending') RETURNING id",
                    (url, cluster_id),
                )
                result = cur.fetchone()
                task_id = result[0] if result else 0
            conn.commit()
        return task_id

    def update_task_status(
        self,
        task_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE seo_tasks SET status = %s, error_message = %s, updated_at = NOW() WHERE id = %s",
                    (status, error_message, task_id),
                )
            conn.commit()

    def get_pending_tasks(self) -> List[Dict]:
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, page_url, cluster_id, status FROM seo_tasks WHERE status = 'pending' ORDER BY created_at"
                )
                rows = cur.fetchall()
        return [
            {"id": r[0], "url": r[1], "cluster_id": r[2], "status": r[3]} for r in rows
        ]

    def merge_html(
        self,
        editable_html: str,
        non_editable_html: str,
    ) -> str:
        soup = BeautifulSoup(non_editable_html, "html.parser")

        body = soup.find("body")
        if not body:
            return editable_html

        body.clear()
        body.append(BeautifulSoup(editable_html, "html.parser"))

        return str(soup)
