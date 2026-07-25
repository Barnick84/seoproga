import pytest
from unittest.mock import patch, MagicMock
from services.billing import BillingService, InsufficientFundsError

def test_deduct_balance_success():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulate successful update where balance was sufficient
        mock_cur.rowcount = 1
        
        result = BillingService.deduct_balance(user_id=1, amount=5.0, description="Test", operation_type="test")
        
        assert result is True
        mock_cur.execute.assert_any_call(
            "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
            (5.0, 1, 5.0)
        )
        mock_conn.commit.assert_called_once()

def test_deduct_balance_insufficient_funds():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulate update failure (insufficient balance)
        mock_cur.rowcount = 0
        
        with pytest.raises(InsufficientFundsError):
            BillingService.deduct_balance(user_id=1, amount=5.0, description="Test", operation_type="test")
            
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

def test_process_webhook_idempotent_already_success():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Order already success
        mock_cur.fetchone.return_value = {"status": "success"}
        
        success, msg = BillingService.process_webhook(order_id="123", amount=10.0, user_id=1)
        
        assert success is True
        assert msg == "Already processed"
        mock_conn.commit.assert_not_called()

def test_process_webhook_success_from_pending():
    with patch("services.billing.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Order pending
        mock_cur.fetchone.return_value = {"status": "pending"}
        # Update successful
        mock_cur.rowcount = 1
        
        success, msg = BillingService.process_webhook(order_id="123", amount=10.0, user_id=1)
        
        assert success is True
        assert msg == "Processed successfully"
        mock_conn.commit.assert_called_once()
