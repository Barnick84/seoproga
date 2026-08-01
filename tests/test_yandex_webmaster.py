from unittest.mock import MagicMock, patch

import pytest

from services.yandex_webmaster import YandexWebmasterClient


@pytest.fixture
def client():
    return YandexWebmasterClient(token="fake_token", user_id=1)


def test_normalize_url_removes_protocol(client):
    assert client._normalize_url("https://example.com/") == "example.com"


def test_normalize_url_removes_port(client):
    assert client._normalize_url("https://example.com:443") == "example.com"
    assert client._normalize_url("http://example.com:80") == "example.com"


def test_normalize_url_lowercases(client):
    assert client._normalize_url("HTTPS://EXAMPLE.COM/Path") == "example.com/path"


def test_list_hosts_calls_api(client):
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hosts": [{"host_id": "example.com"}]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch.object(client, "_get_user_id", return_value="123"):
            hosts = client.list_hosts()

    assert hosts == [{"host_id": "example.com"}]


def test_list_hosts_uses_timeout(client):
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hosts": []}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch.object(client, "_get_user_id", return_value="123"):
            client.list_hosts()

    _, kwargs = mock_get.call_args
    assert kwargs.get("timeout") == 30


def test_get_user_id(client):
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"user_id": "12345"}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        uid = client._get_user_id()

    assert uid == "12345"


def test_fetch_queries_recent_returns_empty_on_404(client):
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with patch.object(client, "_get_user_id", return_value="123"):
            with patch.object(client, "_get_host_id", return_value="host1"):
                queries = client.fetch_queries_recent("https://example.com")

    assert queries == []


def test_save_queries_to_db_counts_new_and_updates(client):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = {}

    with patch("services.yandex_webmaster.Config.get_conn", return_value=mock_conn):
        with patch.object(client, "_get_position_rates", return_value={"new": 0.25, "step": 0.05}):
            added = client.save_queries_to_db(
                [{"query_text": "test kw", "site_url": "example.com"}]
            )

    assert added == 1
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()


def test_save_queries_to_db_updates_existing(client):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = [{"query": "test kw", "id": 42}]

    with patch("services.yandex_webmaster.Config.get_conn", return_value=mock_conn):
        with patch.object(client, "_get_position_rates", return_value={"new": 0.25, "step": 0.05}):
            added = client.save_queries_to_db(
                [{"query_text": "test kw", "avg_position": 5.0, "site_url": "example.com"}]
            )

    assert added == 0


def test_save_queries_to_db_empty_returns_zero(client):
    assert client.save_queries_to_db([]) == 0


def test_calculate_position_cost(client):
    assert client.calculate_position_cost(5.0, 0.05) == 0.05
    assert client.calculate_position_cost(15.0, 0.05) == 0.10
    assert client.calculate_position_cost(0.0, 0.05) == 0.05
