from typing import Tuple

from config import Config


class InsufficientFundsError(Exception):
    pass


class BillingService:
    @staticmethod
    def deduct_balance(user_id: int, amount: float, description: str, operation_type: str) -> bool:
        """
        Atomically deducts balance from a user and records the transaction.
        Raises InsufficientFundsError if balance is too low.
        Returns True if successful.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            # Atomic update checking if balance is sufficient
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
                (amount, user_id, amount),
            )

            if cur.rowcount == 0:
                raise InsufficientFundsError("Insufficient funds or user not found")

            cur.execute(
                "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                (user_id, -amount, description, operation_type),
            )

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def process_webhook(order_id: str, amount: float, user_id: int) -> Tuple[bool, str]:
        """
        Idempotent processing of a payment webhook.
        Returns (success, message)
        """
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            # Check if order already processed
            cur.execute("SELECT status FROM payment_history WHERE order_id = %s", (order_id,))
            result = cur.fetchone()

            if result:
                if result["status"] == "success":
                    return True, "Already processed"

                # If pending, update status and add balance atomically
                cur.execute(
                    "UPDATE payment_history SET status = 'success' WHERE order_id = %s AND status = 'pending'",
                    (order_id,),
                )

                if cur.rowcount > 0:
                    cur.execute(
                        "UPDATE users SET balance = balance + %s WHERE id = %s", (amount, user_id)
                    )
                    cur.execute(
                        "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                        (user_id, amount, f"Top up via Cardlink (Order: {order_id})", "topup"),
                    )
                    conn.commit()
                    return True, "Processed successfully"
                else:
                    return True, "Already processed concurrently"
            else:
                # Order doesn't exist in payment_history, which means it wasn't created via our API.
                # Just insert as success.
                cur.execute(
                    "INSERT INTO payment_history (user_id, amount, order_id, status) VALUES (%s, %s, %s, 'success')",
                    (user_id, amount, order_id),
                )
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s", (amount, user_id)
                )
                cur.execute(
                    "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                    (user_id, amount, f"Top up via Cardlink (Order: {order_id})", "topup"),
                )
                conn.commit()
                return True, "Processed successfully and created"
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
