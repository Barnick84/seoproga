from config import Config


class InsufficientFundsError(Exception):
    """Raised when a charge cannot be applied due to insufficient balance."""

    def __init__(self, message: str, user_id: int, required: float, available: float) -> None:
        super().__init__(message)
        self.user_id = user_id
        self.required = required
        self.available = available

    @property
    def missing(self) -> float:
        return max(self.required - self.available, 0.0)

    def to_dict(self) -> dict:
        return {
            "error": "INSUFFICIENT_FUNDS",
            "message": (
                f"Недостаточно средств. Требуется: {self.required:.2f} ₽, "
                f"доступно: {self.available:.2f} ₽"
            ),
            "required": self.required,
            "available": self.available,
            "missing": self.missing,
        }


class BillingService:
    @staticmethod
    def deduct_balance(
        user_id: int, amount: float, description: str, operation_type: str = "charge"
    ) -> bool:
        """Atomically deduct balance and record the transaction.

        Raises:
            ValueError: if amount is not positive.
            InsufficientFundsError: if balance is too low or user not found.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
                (amount, user_id, amount),
            )

            if cur.rowcount == 0:
                cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"User {user_id} not found")
                balance = float(row["balance"]) if isinstance(row, dict) else float(row[0])
                raise InsufficientFundsError(
                    "Insufficient funds or user not found",
                    user_id=user_id,
                    required=amount,
                    available=balance,
                )

            cur.execute(
                "INSERT INTO billing_history (user_id, amount, description, type) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, -amount, description, operation_type),
            )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
