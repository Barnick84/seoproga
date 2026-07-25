import bcrypt

from config import Config


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    @staticmethod
    def register_user(username: str, email: str, password: str) -> int:
        """
        Registers a new user and returns their ID.
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
    def login(email: str, password: str) -> dict | None:
        """
        Verifies login credentials.
        Returns user dict if successful, None otherwise.
        """
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            if user and AuthService.verify_password(password, user["password"]):
                # Don't return the password hash
                user.pop("password", None)
                return user
            return None
        finally:
            conn.close()

    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> bool:
        """
        Changes a user's password if the old one matches.
        """
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
