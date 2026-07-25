import pytest
from unittest.mock import patch, MagicMock, ANY
from services.auth import AuthService

def test_hash_and_verify():
    password = "secret_password"
    hashed = AuthService.hash_password(password)
    
    assert AuthService.verify_password(password, hashed) is True
    assert AuthService.verify_password("wrong_password", hashed) is False

def test_register_user_success():
    with patch("services.auth.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulating no existing user
        mock_cur.fetchone.return_value = None
        mock_cur.lastrowid = 1
        
        user_id = AuthService.register_user("testuser", "test@example.com", "pass123")
        
        assert user_id == 1
        mock_cur.execute.assert_any_call(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            ("testuser", "test@example.com", ANY)
        )
        mock_conn.commit.assert_called_once()

def test_register_user_exists():
    with patch("services.auth.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulating existing user
        mock_cur.fetchone.return_value = {"id": 1}
        
        with pytest.raises(ValueError, match="Email already exists"):
            AuthService.register_user("testuser", "test@example.com", "pass123")
            
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

def test_login_success():
    with patch("services.auth.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        password = "my_password"
        hashed = AuthService.hash_password(password)
        
        mock_cur.fetchone.return_value = {
            "id": 1,
            "email": "test@example.com",
            "password": hashed
        }
        
        user = AuthService.login("test@example.com", password)
        
        assert user is not None
        assert user["id"] == 1
        assert "password" not in user

def test_change_password_success():
    with patch("services.auth.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        old_password = "old_password"
        hashed = AuthService.hash_password(old_password)
        
        mock_cur.fetchone.return_value = {"password": hashed}
        
        result = AuthService.change_password(1, old_password, "new_password")
        
        assert result is True
        mock_conn.commit.assert_called_once()
