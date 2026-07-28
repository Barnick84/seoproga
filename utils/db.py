import logging
from contextlib import contextmanager

from config import Config

logger = logging.getLogger(__name__)


@contextmanager
def get_db_cursor(dictionary=True, commit=False):
    """
    Контекстный менеджер для безопасной работы с базой данных.
    Автоматически закрывает курсор и соединение.
    Осуществляет commit() при успешном завершении, если commit=True.
    Делает rollback() при возникновении исключения.
    """
    conn = Config.get_conn()
    cur = None
    try:
        if Config.DB_TYPE == "postgresql":
            if dictionary:
                import psycopg2.extras

                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                cur = conn.cursor()
        elif Config.DB_TYPE == "mysql":
            if dictionary:
                import pymysql.cursors

                cur = conn.cursor(pymysql.cursors.DictCursor)
            else:
                import pymysql.cursors

                cur = conn.cursor(pymysql.cursors.Cursor)
        else:
            cur = conn.cursor()
        yield conn, cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
