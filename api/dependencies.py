import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel
load_dotenv()

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
except ImportError:
    class DummyLimiter:
        def limit(self, *args, **kwargs):
            return lambda func: func
    limiter = DummyLimiter()

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET must be set in .env. "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", 120))


class TokenData(BaseModel):
    user_id: int
    username: str
    jti: str = ""


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire, "jti": secrets.token_urlsafe(16)})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def _is_token_revoked(jti: str) -> bool:
    """Return True if token is revoked OR if revocation status cannot be verified (fail-closed)."""
    from config import Config

    try:
        conn = Config.get_conn()
    except Exception as e:
        logger.error("Failed to connect to DB for token revocation check: %s", e)
        return True

    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = %s AND expires_at > %s",
                (jti, datetime.now()),
            )
            return cur.fetchone() is not None
        except Exception as e:
            logger.error("Failed to check token revocation for jti=%s: %s", jti, e)
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error("Token revocation check inaccessible, treating as revoked: %s", e)
        return True


def revoke_token(jti: str, exp: int) -> bool:
    """Persist revocation. Returns False if persistence failed (token remains valid)."""
    from config import Config

    try:
        conn = Config.get_conn()
    except Exception as e:
        logger.error("Failed to connect to DB for token revocation: %s", e)
        return False

    try:
        cur = conn.cursor()
        try:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
            cur.execute(
                "INSERT IGNORE INTO token_blacklist (jti, expires_at) VALUES (%s, %s)",
                (jti, expires_at),
            )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error("Failed to revoke token jti=%s: %s", jti, e)
            return False
        finally:
            conn.close()
    except Exception as e:
        logger.error("Token revocation inaccessible: %s", e)
        return False


async def get_current_user(authorization: Optional[str] = Header(None)) -> TokenData:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")

    parts = authorization.split()
    if len(parts) == 1:
        token = parts[0]
    elif len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    else:
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("user_id")
        username: str | None = payload.get("username")
        jti: str = payload.get("jti", "")
        if user_id is None or username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        if jti and _is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        return TokenData(user_id=user_id, username=username, jti=jti)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


async def verify_admin_token(authorization: Optional[str] = Header(None)) -> bool:
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")

    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    else:
        token = authorization

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        jti: str = payload.get("jti", "")
        if jti and _is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        if not payload.get("is_admin"):
            raise HTTPException(status_code=403, detail="Unauthorized admin access")
        return True
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate admin credentials")


async def verify_domain_ownership(
    domain: str,
    current_user: TokenData = Depends(get_current_user),
) -> str:
    from utils.db import get_db_cursor
    from utils.helpers import extract_domain

    normalized_domain = extract_domain(domain)

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "SELECT 1 FROM sites WHERE user_id = %s AND domain = %s",
            (current_user.user_id, normalized_domain),
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=403, detail="Forbidden: You do not have access to this domain."
            )

    return normalized_domain
