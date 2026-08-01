import json
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    XMLRIVER_USER = os.getenv("XMLRIVER_USER", "")
    XMLRIVER_KEY = os.getenv("XMLRIVER_KEY", "")
    XMLRIVER_REGION = int(os.getenv("XMLRIVER_REGION", 213))
    XMLRIVER_ENGINE = os.getenv("XMLRIVER_ENGINE", "yandex")

    YANDEX_TOKEN = os.getenv("YANDEX_OAUTH_TOKEN", "")
    YANDEX_SITE = os.getenv("YANDEX_SITE_URL", "")

    PG_PASS = os.getenv("PG_PASSWORD", "")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_DB = os.getenv("MYSQL_DBNAME", "seo_auto")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASS = os.getenv("MYSQL_PASSWORD", "")

    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.4))
    SERP_TOP_N = int(os.getenv("SERP_TOP_N", 10))
    CONTENT_ANALYSIS_COMPETITORS = int(os.getenv("CONTENT_ANALYSIS_COMPETITORS", 15))
    CACHE_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", 7))
    XMLRIVER_REQUEST_DELAY = float(os.getenv("XMLRIVER_REQUEST_DELAY", 1.5))

    PG_HOST = os.getenv("PG_HOST", "localhost")
    PG_PORT = int(os.getenv("PG_PORT", 5432))
    PG_DB = os.getenv("PG_DB", "seo_auto")
    PG_USER = os.getenv("PG_USER", "postgres")

    _raw_mysql_host = os.getenv("MYSQL_HOST", "")
    _raw_mysql_pass = os.getenv("MYSQL_PASSWORD", "")
    DB_TYPE = "postgresql" if PG_PASS else ("mysql" if _raw_mysql_host else "sqlite")

    MIRATEXT_API_KEY = os.getenv("MIRATEXT_API_KEY", "")
    MIRATEXT_REGION = int(os.getenv("MIRATEXT_REGION", 213))
    MIRATEXT_MAX_WAIT = int(os.getenv("MIRATEXT_MAX_WAIT", 180))
    MIRATEXT_POLL_INTERVAL = int(os.getenv("MIRATEXT_POLL_INTERVAL", 3))

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.2))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 8192))

    EXCLUDED_DOMAINS: list[str] = []

    @classmethod
    def get_excluded_domains(cls) -> list[str]:
        if not cls.EXCLUDED_DOMAINS:
            path = os.path.join(os.path.dirname(__file__), "data", "excluded_domains.json")
            try:
                with open(path, encoding="utf-8") as f:
                    cls.EXCLUDED_DOMAINS = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                cls.EXCLUDED_DOMAINS = []
        return cls.EXCLUDED_DOMAINS

    @classmethod
    def get_pg_dsn(cls):
        return (
            f"host={cls.PG_HOST} port={cls.PG_PORT} "
            f"dbname={cls.PG_DB} user={cls.PG_USER} password={cls.PG_PASS}"
        )

    _mysql_pool = None
    _pg_pool = None

    @classmethod
    def get_mysql_conn(cls):
        if cls._mysql_pool is None:
            import pymysql
            from dbutils.pooled_db import PooledDB

            cls._mysql_pool = PooledDB(
                creator=pymysql,
                maxconnections=20,
                mincached=0,
                maxcached=10,
                blocking=True,
                host=cls.MYSQL_HOST,
                port=cls.MYSQL_PORT,
                user=cls.MYSQL_USER,
                password=cls.MYSQL_PASS,
                database=cls.MYSQL_DB,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
        return cls._mysql_pool.connection()

    @classmethod
    def get_pg_conn(cls):
        if cls._pg_pool is None:
            import psycopg2
            from dbutils.pooled_db import PooledDB

            cls._pg_pool = PooledDB(
                creator=psycopg2,
                maxconnections=20,
                mincached=0,
                maxcached=10,
                blocking=True,
                host=cls.PG_HOST,
                port=cls.PG_PORT,
                dbname=cls.PG_DB,
                user=cls.PG_USER,
                password=cls.PG_PASS,
            )
        return cls._pg_pool.connection()

    @classmethod
    def get_conn(cls):
        if cls.DB_TYPE == "postgresql":
            return cls.get_pg_conn()
        if cls.DB_TYPE == "mysql":
            return cls.get_mysql_conn()
        raise RuntimeError(
            f"Unsupported DB_TYPE='{cls.DB_TYPE}'. Set MYSQL_HOST or PG_PASSWORD in .env"
        )

    @classmethod
    def validate(cls, mode: str = "xmlriver"):
        if mode == "xmlriver":
            if not cls.XMLRIVER_USER or not cls.XMLRIVER_KEY:
                raise ValueError("Не заданы XMLRIVER_USER или XMLRIVER_KEY в .env")
        elif mode == "yandex":
            if not cls.YANDEX_TOKEN or not cls.YANDEX_SITE:
                raise ValueError("Не заданы YANDEX_OAUTH_TOKEN или YANDEX_SITE_URL в .env")
        elif mode == "miratext":
            if not cls.MIRATEXT_API_KEY:
                raise ValueError("Не задан MIRATEXT_API_KEY в .env")
            if not cls.OPENAI_API_KEY:
                raise ValueError("Не задан OPENAI_API_KEY в .env")
        return True
