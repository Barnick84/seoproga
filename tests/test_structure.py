import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test_secret_key_12345678901234567890")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import TokenData, get_current_user
from api.routers.structure import router
from config import Config

app = FastAPI()
app.include_router(router)

# Override auth dependency
app.dependency_overrides[get_current_user] = lambda: TokenData(user_id=1, username="testuser")

client = TestClient(app)


def test_get_site_structure_empty():
    with patch("api.routers.structure.get_db_cursor") as mock_db:
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_db.return_value.__enter__.return_value = (MagicMock(), mock_cur)

        response = client.get("/api/site-structure?site_url=example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["structure"] == []


def test_get_site_structure_exists():
    with patch("api.routers.structure.get_db_cursor") as mock_db:
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {
            "structure_json": json.dumps([{"id": "1", "title": "Главная"}]),
            "updated_at": "2026-08-01 12:00:00",
        }
        mock_db.return_value.__enter__.return_value = (MagicMock(), mock_cur)

        response = client.get("/api/site-structure?site_url=example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert len(data["structure"]) == 1
        assert data["structure"][0]["title"] == "Главная"


def test_save_site_structure():
    with patch("api.routers.structure.get_db_cursor") as mock_db:
        mock_cur = MagicMock()
        mock_db.return_value.__enter__.return_value = (MagicMock(), mock_cur)

        payload = {
            "site_url": "example.com",
            "structure": [{"id": "1", "title": "Главная", "url": "/"}]
        }
        response = client.post("/api/site-structure/save", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True


def test_generate_site_structure_no_openai_key():
    with patch.object(Config, "OPENAI_API_KEY", ""):
        response = client.post(
            "/api/site-structure/generate",
            json={"site_url": "example.com", "mode": "auto"}
        )
        assert response.status_code == 400
        assert "OPENAI_API_KEY не настроен" in response.json()["detail"]


def test_generate_site_structure_no_clusters():
    with patch.object(Config, "OPENAI_API_KEY", "dummy_key"):
        with patch("api.routers.structure.get_db_cursor") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.return_value = []
            mock_db.return_value.__enter__.return_value = (MagicMock(), mock_cur)

            response = client.post(
                "/api/site-structure/generate",
                json={"site_url": "example.com", "mode": "auto"}
            )
            assert response.status_code == 400
            assert "отсутствуют кластеры" in response.json()["detail"]


def test_generate_site_structure_success():
    with patch.object(Config, "OPENAI_API_KEY", "dummy_key"):
        with patch("api.routers.structure.get_db_cursor") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.return_value = [
                {
                    "cluster_id": 1,
                    "main_kw": "купить авто",
                    "kw_count": 5,
                    "cluster_name": "Автомобили",
                    "target_url": "/auto",
                }
            ]
            mock_db.return_value.__enter__.return_value = (MagicMock(), mock_cur)

            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(
                    message=MagicMock(
                        content=json.dumps({
                            "structure": [
                                {
                                    "id": "root",
                                    "title": "Главная",
                                    "url": "/",
                                    "is_folder": True,
                                    "page_type": "Главная",
                                    "children": [
                                        {
                                            "id": "auto",
                                            "title": "Автомобили",
                                            "url": "/auto",
                                            "is_folder": False,
                                            "cluster_id": "1",
                                            "page_type": "Категория",
                                        }
                                    ],
                                }
                            ]
                        })
                    )
                )
            ]

            with patch("api.routers.structure.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                response = client.post(
                    "/api/site-structure/generate",
                    json={"site_url": "example.com", "mode": "auto"}
                )
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert len(data["structure"]) == 1
                assert data["structure"][0]["title"] == "Главная"
