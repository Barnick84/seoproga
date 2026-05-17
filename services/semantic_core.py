# services/semantic_core.py
"""Semantic core management for Yandex Webmaster queries.

Provides a thin wrapper around PostgreSQL to store clusters of keywords
and their SERP representatives.
"""
import json
from typing import List, Dict, Any
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
                keywords JSONB NOT NULL,
                serp_representative JSONB NOT NULL
            );
        """
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
            conn.commit()

    def get_clusters(self) -> List[Dict[str, Any]]:
        """Return all existing clusters as a list of dicts.

        Each dict contains ``id``, ``keywords`` (list[str]) and ``serp_representative`` (list[str]).
        """
        select_sql = "SELECT id, keywords, serp_representative FROM semantic_clusters;"
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(select_sql)
                rows = cur.fetchall()
        clusters = []
        for row in rows:
            cid, kw_json, serp_json = row
            clusters.append({
                "id": cid,
                "keywords": kw_json,  # already a Python list via psycopg2 Json adaptation
                "serp_representative": serp_json,
            })
        return clusters

    def save_clusters(self, clusters: List[Dict[str, Any]]):
        """Replace all clusters with the provided list.

        For simplicity we truncate the table and bulk‑insert the new set.
        """
        truncate_sql = "TRUNCATE TABLE semantic_clusters RESTART IDENTITY;"
        insert_sql = """
            INSERT INTO semantic_clusters (keywords, serp_representative)
            VALUES %s;
        """
        values = [(
            json.dumps(c["keywords"]),
            json.dumps(c["serp_representative"]),
        ) for c in clusters]
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(truncate_sql)
                if values:
                    execute_values(cur, insert_sql, values, page_size=500)
            conn.commit()
