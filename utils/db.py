import logging
from contextlib import contextmanager

from config import Config

logger = logging.getLogger(__name__)


def _make_cursor(conn, dictionary: bool):
    if Config.DB_TYPE == "postgresql":
        import psycopg2.extras

        if dictionary:
            return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return conn.cursor()
    if Config.DB_TYPE == "mysql":
        import pymysql.cursors

        if dictionary:
            return conn.cursor(pymysql.cursors.DictCursor)
        return conn.cursor(pymysql.cursors.Cursor)
    return conn.cursor()


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
        cur = _make_cursor(conn, dictionary)
        yield conn, cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Database transaction error: %s", e)
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
