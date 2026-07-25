import hashlib
import logging

import bcrypt

from config import Config

logger = logging.getLogger(__name__)

_LEGACY_SALT_LEN = 32


def _verify_legacy(password: str, stored: str) -> bool:
    """Verify PBKDF2-HMAC-SHA256 hash from legacy Node.js system.

    Format: salt(32 hex) + pbkdf2_hmac(sha256, 100000 iters).hex()  = 96 chars total.
    """
    if len(stored) != 96:
        return False
    salt = stored[:_LEGACY_SALT_LEN]
    expected_hex = stored[_LEGACY_SALT_LEN:]
    try:
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return derived.hex() == expected_hex
    except Exception:
        return False


def _is_legacy_hash(stored: str) -> bool:
    return len(stored) == 96 and not stored.startswith("$2")


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        if not hashed:
            return False
        if _is_legacy_hash(hashed):
            return _verify_legacy(password, hashed)
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def _migrate_to_bcrypt(user_id: int, password: str) -> None:
        """Silently re-hash legacy password to bcrypt on successful login."""
        try:
            new_hash = AuthService.hash_password(password)
            conn = Config.get_conn()
            cur = conn.cursor()
            try:
                cur.execute("UPDATE users SET password = %s WHERE id = %s", (new_hash, user_id))
                conn.commit()
                logger.info("Migrated password to bcrypt for user_id=%s", user_id)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to migrate password for user_id=%s: %s", user_id, e)

    @staticmethod
    def register_user(username: str, email: str, password: str) -> int:
        """Registers a new user and returns their ID.
        Raises ValueError if email exists.
        """
        hashed = AuthService.hash_password(password)
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise ValueError("Email already exists")

            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed),
            )
            user_id = cur.lastrowid
            conn.commit()
            return user_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def login(identifier: str, password: str) -> dict | None:
        """Verifies login credentials by username or email.
        Returns user dict if successful, None otherwise.
        Migrates legacy PBKDF2 hashes to bcrypt on first successful login.
        """
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM users WHERE username = %s OR email = %s",
                (identifier, identifier),
            )
            user = cur.fetchone()
        finally:
            conn.close()

        if not user:
            return None

        stored_hash = user.get("password", "")
        if not AuthService.verify_password(password, stored_hash):
            return None

        if _is_legacy_hash(stored_hash):
            AuthService._migrate_to_bcrypt(user["id"], password)

        user.pop("password", None)
        return user

    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> bool:
        """Changes a user's password if the old one matches."""
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()

            if not user or not AuthService.verify_password(old_password, user["password"]):
                return False

            hashed_new = AuthService.hash_password(new_password)
            cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_new, user_id))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
