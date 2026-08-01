from unittest.mock import MagicMock, patch

import pytest

from services.billing import BillingService, InsufficientFundsError


def test_deduct_balance_success():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate successful update where balance was sufficient
        mock_cur.rowcount = 1

        result = BillingService.deduct_balance(
            user_id=1, amount=5.0, description="Test", operation_type="test"
        )

        assert result is True
        mock_cur.execute.assert_any_call(
            "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s", (5.0, 1, 5.0)
        )
        mock_conn.commit.assert_called_once()


def test_deduct_balance_insufficient_funds():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate update failure (insufficient balance), then SELECT returns balance
        mock_cur.rowcount = 0
        mock_cur.fetchone.return_value = {"balance": 2.0}

        with pytest.raises(InsufficientFundsError) as exc_info:
            BillingService.deduct_balance(
                user_id=1, amount=5.0, description="Test", operation_type="test"
            )

        assert exc_info.value.required == 5.0
        assert exc_info.value.available == 2.0
        assert exc_info.value.missing == 3.0
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()


def test_deduct_balance_user_not_found():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_cur.rowcount = 0
        mock_cur.fetchone.return_value = None

        with pytest.raises(ValueError, match="User 1 not found"):
            BillingService.deduct_balance(
                user_id=1, amount=5.0, description="Test", operation_type="test"
            )

        mock_conn.rollback.assert_called_once()


def test_deduct_balance_rejects_non_positive_amount():
    with pytest.raises(ValueError, match="Amount must be positive"):
        BillingService.deduct_balance(user_id=1, amount=0.0, description="Test")


def test_insufficient_funds_error_to_dict():
    err = InsufficientFundsError("msg", user_id=1, required=10.0, available=3.0)
    data = err.to_dict()
    assert data["error"] == "INSUFFICIENT_FUNDS"
    assert data["required"] == 10.0
    assert data["available"] == 3.0
    assert data["missing"] == 7.0
    assert "10.00" in data["message"] or "10.0" in data["message"]
