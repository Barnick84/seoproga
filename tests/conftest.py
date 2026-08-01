from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    """Patch Config.get_conn() with a MagicMock connection and cursor.

    Yields a dict with ``conn``, ``cur`` and ``get_conn`` so tests can set
    ``cur.fetchone``/``cur.fetchall``/``cur.rowcount`` etc. per test.
    """
    with patch("config.Config.get_conn") as get_conn:
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        get_conn.return_value = conn
        yield {
            "conn": conn,
            "cur": cur,
            "get_conn": get_conn,
        }
