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
        cur = conn.cursor(dictionary=dictionary)
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
