from unittest.mock import MagicMock, patch

import pytest

from services.xmlriver_client import XmlriverClient


@pytest.fixture
def mock_cache():
    with patch("services.xmlriver_client.SERPCache") as mc:
        cache = MagicMock()
        cache.get.return_value = None
        mc.return_value = cache
        yield cache


@pytest.fixture
def client(mock_cache):
    return XmlriverClient(max_retries=2, retry_delay=0.01)


def test_fetch_serp_returns_urls(client):
    fake_xml = {
        "yandexsearch": {
            "response": {
                "results": {
                    "grouping": {
                        "group": [
                            {
                                "doc": [
                                    {"url": "https://example.com/1", "contenttype": "organic"},
                                    {"url": "https://example.com/2", "contenttype": "organic"},
                                ]
                            }
                        ]
                    }
                }
            }
        }
    }
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = b"ignored"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch("services.xmlriver_client.xmltodict.parse", return_value=fake_xml):
            urls = client.fetch_serp("test kw", use_cache=False)

    assert len(urls) == 2
    assert "example.com/1" in urls


def test_fetch_serp_uses_cache(client, mock_cache):
    mock_cache.get.return_value = ["example.com/cached"]
    urls = client.fetch_serp("cached kw", use_cache=True)
    assert urls == ["example.com/cached"]
    mock_cache.get.assert_called_once()


def test_fetch_serp_sets_cache(client, mock_cache):
    fake_xml = {
        "yandexsearch": {
            "response": {
                "results": {
                    "grouping": {
                        "group": [
                            {
                                "doc": [
                                    {"url": "https://example.com/1", "contenttype": "organic"},
                                ]
                            }
                        ]
                    }
                }
            }
        }
    }
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = b"ignored"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch("services.xmlriver_client.xmltodict.parse", return_value=fake_xml):
            client.fetch_serp("test kw", use_cache=True)

    mock_cache.set.assert_called_once()


def test_fetch_serp_retries_on_error(client):
    with patch.object(client.session, "get") as mock_get:
        mock_get.side_effect = ConnectionError("timeout")
        with pytest.raises(ConnectionError):
            client.fetch_serp("test kw", use_cache=False)
    assert mock_get.call_count == 2


def test_fetch_serp_fatal_error_no_retry(client):
    fake_xml = {"yandexsearch": {"response": {"error": {"@code": "400", "#text": "bad request"}}}}
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = b"ignored"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch("services.xmlriver_client.xmltodict.parse", return_value=fake_xml):
            with pytest.raises(ValueError, match="XMLRiver Fatal Error"):
                client.fetch_serp("test kw", use_cache=False)
    assert mock_get.call_count == 1


def test_fetch_serp_empty_response(client):
    fake_xml = {"yandexsearch": {"response": {"results": {"grouping": {"group": []}}}}}
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = b"ignored"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch("services.xmlriver_client.xmltodict.parse", return_value=fake_xml):
            urls = client.fetch_serp("test kw", use_cache=False)

    assert urls == []


def test_fetch_serp_rate_limiting(client):
    client.min_delay = 0.5
    fake_xml = {
        "yandexsearch": {
            "response": {
                "results": {
                    "grouping": {
                        "group": [
                            {"doc": [{"url": "https://example.com/1", "contenttype": "organic"}]}
                        ]
                    }
                }
            }
        }
    }
    responses = []

    def slow_get(*a, **kw):
        responses.append(1)
        mock_resp = MagicMock()
        mock_resp.content = b"ignored"
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    with patch.object(client.session, "get", side_effect=slow_get):
        with patch("services.xmlriver_client.xmltodict.parse", return_value=fake_xml):
            with patch("services.xmlriver_client.time") as mock_time:
                mock_time.time.side_effect = [0.0, 0.0, 0.3, 0.3]
                client.fetch_serp("kw1", use_cache=False)
                client.fetch_serp("kw2", use_cache=False)

    assert len(responses) == 2
