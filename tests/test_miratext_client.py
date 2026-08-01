from unittest.mock import MagicMock, patch

import pytest

from services.miratext_client import MiratextClient


@pytest.fixture
def client():
    with patch("services.miratext_client.Config.MIRATEXT_API_KEY", "fake_key"):
        with patch("services.miratext_client.Config.MIRATEXT_REGION", 213):
            with patch("services.miratext_client.Config.MIRATEXT_MAX_WAIT", 5):
                with patch("services.miratext_client.Config.MIRATEXT_POLL_INTERVAL", 0.1):
                    yield MiratextClient()


def test_submit_analysis_returns_task_id(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "accepted", "data": {"task_id": "abc123"}}
        mock_resp.raise_for_status.return_value = None
        mock_request.return_value = mock_resp

        task_id = client.submit_analysis("some text", ["kw1", "kw2"])

    assert task_id == "abc123"


def test_submit_analysis_raises_on_error(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "error", "error": "bad request"}
        mock_resp.raise_for_status.return_value = None
        mock_request.return_value = mock_resp

        with pytest.raises(ValueError, match="Miratext error"):
            client.submit_analysis("text", ["kw"])


def test_get_result_polls_until_done(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = [
            {"status": "progress"},
            {"status": "done", "data": {"tz": {"wordsCount": 100}}},
        ]
        mock_request.return_value = mock_resp

        result = client.get_result("task1")

    assert result == {"tz": {"wordsCount": 100}}


def test_get_result_raises_on_error(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "error", "error": "processing failed"}
        mock_request.return_value = mock_resp

        with pytest.raises(RuntimeError, match="Miratext analysis error"):
            client.get_result("task1")


def test_get_result_times_out(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "progress"}
        mock_request.return_value = mock_resp

        with pytest.raises(TimeoutError, match="Miratext analysis timeout"):
            client.get_result("task1")


def test_parse_recommendations_filters_target_keywords(client):
    raw = {
        "tz": {
            "wordsCount": 500,
            "keywordsAll": [
                {"word": "SEO", "recomended": 5, "my_count": 2, "density": 1.0},
                {"word": "optimization", "recomended": 3, "my_count": 0, "density": 0.5},
            ],
        },
        "status": "done",
    }
    result = client._parse_recommendations(raw, ["seo"])
    assert len(result["keywords"]) == 1
    assert result["keywords"][0]["keyword"] == "SEO"
    assert result["keywords"][0]["need_to_add"] == 3


def test_request_uses_timeout(client):
    with patch.object(client.session, "request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}
        mock_request.return_value = mock_resp

        client._request("GET", "/test")

    _, kwargs = mock_request.call_args
    assert kwargs.get("timeout") == 30
