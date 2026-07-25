# services/semantic_core.py
"""Semantic core management for Yandex Webmaster queries.

Provides a thin wrapper around PostgreSQL to store clusters of keywords
and their SERP representatives.
"""

import json
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import execute_values

from config import Config


class SemanticCoreManager:
    """Handles CRUD operations for the semantic core.

    The schema (PostgreSQL) is simple:
        CREATE TABLE IF NOT EXISTS semantic_clusters (
            id SERIAL PRIMARY KEY,
            keywords JSONB NOT NULL,               -- list of keyword strings
            serp_representative JSONB NOT NULL      -- list of SERP URLs/domains
        );
    """

    def __init__(self):
        self.dsn = Config.get_pg_dsn()
        self._ensure_tables()

    def _ensure_tables(self):
        """Create the table if it does not exist."""
        create_sql = """
            CREATE TABLE IF NOT EXISTS semantic_clusters (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                site_url TEXT,
                keywords JSONB NOT NULL,
                serp_representative JSONB NOT NULL
            );
        """
        alter_sql1 = "ALTER TABLE semantic_clusters ADD COLUMN IF NOT EXISTS user_id INTEGER;"
        alter_sql2 = "ALTER TABLE semantic_clusters ADD COLUMN IF NOT EXISTS site_url TEXT;"
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
                try:
                    cur.execute(alter_sql1)
                    cur.execute(alter_sql2)
                except Exception:
                    pass
            conn.commit()

    def get_clusters(self, user_id: int, site_url: str) -> List[Dict[str, Any]]:
        """Return all existing clusters as a list of dicts.

        Each dict contains ``id``, ``keywords`` (list[str]) and ``serp_representative`` (list[str]).
        """
        select_sql = "SELECT id, keywords, serp_representative FROM semantic_clusters WHERE user_id = %s AND site_url = %s;"
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(select_sql, (user_id, site_url))
                rows = cur.fetchall()
        clusters = []
        for row in rows:
            cid, kw_json, serp_json = row
            clusters.append(
                {
                    "id": cid,
                    "keywords": kw_json,  # already a Python list via psycopg2 Json adaptation
                    "serp_representative": serp_json,
                }
            )
        return clusters

    def save_clusters(self, clusters: List[Dict[str, Any]], user_id: int, site_url: str):
        """Replace all clusters with the provided list.

        For simplicity we delete the previous records for user_id and site_url and bulk-insert the new set.
        """
        delete_sql = "DELETE FROM semantic_clusters WHERE user_id = %s AND site_url = %s;"
        insert_sql = """
            INSERT INTO semantic_clusters (user_id, site_url, keywords, serp_representative)
            VALUES %s;
        """
        values = [
            (
                user_id,
                site_url,
                json.dumps(c["keywords"]),
                json.dumps(c["serp_representative"]),
            )
            for c in clusters
        ]
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (user_id, site_url))
                if values:
                    execute_values(cur, insert_sql, values, page_size=500)
            conn.commit()
