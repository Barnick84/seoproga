# config.py
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

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_DB = os.getenv("MYSQL_DBNAME", "seo_auto")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASS = os.getenv("MYSQL_PASSWORD", "")

    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.4))
    SERP_TOP_N = 10
    CACHE_TTL_DAYS = 7

    CACHE_DB_PATH = "data/serp_cache.db"
    USE_SQLITE = not (PG_PASS or MYSQL_PASS or os.getenv("MYSQL_HOST"))
    DB_TYPE = "mysql" if MYSQL_HOST and MYSQL_USER else ("postgresql" if PG_PASS else "sqlite")

    MIRATEXT_API_KEY = os.getenv("MIRATEXT_API_KEY", "")
    MIRATEXT_REGION = int(os.getenv("MIRATEXT_REGION", 213))
    MIRATEXT_MAX_WAIT = int(os.getenv("MIRATEXT_MAX_WAIT", 180))
    MIRATEXT_POLL_INTERVAL = int(os.getenv("MIRATEXT_POLL_INTERVAL", 3))

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.2))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 8192))

    EXCLUDED_DOMAINS = [
        "yandex.ru", "avito.ru", "ya.ru", "cian.ru", "2gis.ru", "vk.com",
        "superjob.ru", "hh.ru", "youtube.com", "tutu.ru", "wikipedia.org",
        "travelata.ru", "dzen.ru", "ok.ru", "academic.ru", "otzovik.com",
        "irecommend.ru", "ozon.ru", "t.me", "citilink.ru", "mvideo.ru",
        "dns-shop.ru", "wildberries.ru", "mail.ru", "sravni.ru", "aliexpress.ru",
        "auto.ru", "drom.ru", "drive2.ru", "youla.ru", "google.com", "zoon.ru",
        "gosuslugi.ru", "rambler.ru", "gismeteo.ru", "google.ru", "pikabu.ru",
        "prodoctorov.ru", "domclick.ru", "profi.ru", "yell.ru", "rutube.ru",
        "tripadvisor.ru", "flamp.ru", "spr.ru", "yelp.com", "tulp.ru", "apoi.ru",
        "vseotzyvy.ru", "kupilskazal.ru", "imho24.ru", "otzyv.com",
        "spasibovsem.ru", "sites.reviews", "price.ru", "pulscen.ru", "tiu.ru",
        "aport.ru", "4geo.ru", "rosfirm.ru", "maxi-karta.ru", "spravka.me",
        "allinform.ru", "spravker.ru", "orgpage.ru", "ypag.ru", "foursquare.com",
        "all.biz", "altergeo.ru", "gmstar.ru", "toster.ru", "ask.fm", "twoo.com",
        "thequestion.ru", "genon.ru"
    ]

    @classmethod
    def get_pg_dsn(cls):
        return (
            f"host={cls.PG_HOST} port={cls.PG_PORT} "
            f"dbname={cls.PG_DB} user={cls.PG_USER} password={cls.PG_PASS}"
        )

    @classmethod
    def get_mysql_conn(cls):
        import pymysql
        return pymysql.connect(
            host=cls.MYSQL_HOST,
            port=cls.MYSQL_PORT,
            user=cls.MYSQL_USER,
            password=cls.MYSQL_PASS,
            database=cls.MYSQL_DB,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )

    @classmethod
    def validate(cls, mode: str = "xmlriver"):
        if mode == "xmlriver":
            if not cls.XMLRIVER_USER or not cls.XMLRIVER_KEY:
                raise ValueError("❌ Не заданы XMLRIVER_USER или XMLRIVER_KEY в .env")
        elif mode == "yandex":
            if not cls.YANDEX_TOKEN or not cls.YANDEX_SITE:
                raise ValueError(
                    "❌ Не заданы YANDEX_OAUTH_TOKEN или YANDEX_SITE_URL в .env"
                )
        elif mode == "miratext":
            if not cls.MIRATEXT_API_KEY:
                raise ValueError("❌ Не задан MIRATEXT_API_KEY в .env")
            if not cls.OPENAI_API_KEY:
                raise ValueError("❌ Не задан OPENAI_API_KEY в .env")
        return True
