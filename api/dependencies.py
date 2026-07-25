import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

_DEFAULT_SECRET = secrets.token_urlsafe(32)
SECRET_KEY = os.environ.get("JWT_SECRET", _DEFAULT_SECRET)
if os.environ.get("JWT_SECRET") is None:
    _unset = not os.path.exists(".env")
    if _unset:
        import warnings

        warnings.warn(
            "JWT_SECRET not set. Using random ephemeral secret. "
            "All sessions will be invalidated on server restart. "
            "Set JWT_SECRET in .env for persistent sessions.",
            stacklevel=2,
        )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", 120))  # 2h default


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
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _is_token_revoked(jti: str) -> bool:
    try:
        from config import Config

        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = %s AND expires_at > %s",
                (jti, datetime.now()),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False


def revoke_token(jti: str, exp: int) -> None:
    try:
        from config import Config

        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
            cur.execute(
                "INSERT IGNORE INTO token_blacklist (jti, expires_at) VALUES (%s, %s)",
                (jti, expires_at),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("user_id")
        username: str | None = payload.get("username")
        jti: str = payload.get("jti", "")
        if user_id is None or username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        if jti and _is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        token_data = TokenData(user_id=user_id, username=username, jti=jti)
        return token_data
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token has expired") from e
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Could not validate credentials") from e


async def verify_admin_token(authorization: Optional[str] = Header(None)) -> bool:
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")

    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    else:
        token = authorization

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti: str = payload.get("jti", "")
        if jti and _is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        if not payload.get("is_admin"):
            raise HTTPException(status_code=401, detail="Unauthorized admin access")
        return True
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token has expired") from e
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Could not validate admin credentials") from e


async def verify_domain_ownership(
    domain: str,
    current_user: TokenData = Depends(get_current_user),  # noqa: B008
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
