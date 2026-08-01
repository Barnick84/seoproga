import logging
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from api.dependencies import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    JWT_SECRET,
    TokenData,
    create_access_token,
    get_current_user,
    limiter,
    revoke_token,
)
from services.auth import AuthService
from utils.db import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Users"])


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v or len(v) < 4:
            raise ValueError("Password must be at least 4 characters")
        return v


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""
    yandex_token: Optional[str] = ""

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not v or len(v) < 2:
            raise ValueError("Username must be at least 2 characters")
        if not v.isalnum():
            raise ValueError("Username must be alphanumeric")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class TokenResponse(BaseModel):
    success: bool
    session: str
    user_id: int
    username: str
    tokens: Optional[dict] = None


class UserInfoResponse(BaseModel):
    success: bool
    user: dict


@router.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register(req: RegisterRequest, request: Request):
    try:
        email = req.email if req.email else ""
        user_id = AuthService.register_user(req.username, email, req.password)
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"user_id": user_id, "username": req.username}, expires_delta=access_token_expires
        )
        return TokenResponse(
            success=True, session=access_token, user_id=user_id, username=req.username
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Registration failed: %s", e)
        raise HTTPException(status_code=500, detail="Registration failed due to server error")


@router.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(req: LoginRequest, request: Request):
    user_data = AuthService.login(req.username, req.password)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"user_id": user_data["id"], "username": user_data["username"]},
        expires_delta=access_token_expires,
    )

    return TokenResponse(
        success=True,
        session=access_token,
        user_id=user_data["id"],
        username=user_data["username"],
        tokens={},
    )


@router.get("/api/auth/session")
@limiter.limit("30/minute")
async def get_session(request: Request, current_user: TokenData = Depends(get_current_user)):
    return {
        "success": True,
        "authenticated": True,
        "user_id": current_user.user_id,
        "username": current_user.username,
    }


@router.post("/api/auth/logout")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    authorization: str | None = Header(None),
):
    if authorization and current_user.jti:
        try:
            parts = authorization.split()
            token_str = parts[1] if len(parts) == 2 else authorization
            payload = jwt.decode(token_str, JWT_SECRET, algorithms=[ALGORITHM])
            exp = payload.get("exp", 0)
        except Exception:
            exp = 0
        revoked = revoke_token(current_user.jti, exp)
        if not revoked:
            logger.warning(
                "Logout: token revocation failed for user_id=%s jti=%s; token remains valid until expiry.",
                current_user.user_id,
                current_user.jti,
            )
    return {"success": True, "message": "Logged out"}


@router.get("/api/user-info", response_model=UserInfoResponse)
@limiter.limit("30/minute")
async def get_user_info(request: Request, current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT username, balance FROM users WHERE id = %s", (current_user.user_id,)
            )
            user = cur.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserInfoResponse(success=True, user=user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get user info for %s: %s", current_user.user_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/user/settings")
@limiter.limit("30/minute")
async def get_user_settings(request: Request, current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT yandex_token FROM users WHERE id = %s", (current_user.user_id,))
            user_row = cur.fetchone()

            cur.execute("SELECT domain FROM sites WHERE user_id = %s", (current_user.user_id,))
            sites = [row["domain"] for row in cur.fetchall()]

        yandex_token = user_row["yandex_token"] if user_row and user_row["yandex_token"] else ""
        masked = yandex_token[:6] + "..." + yandex_token[-4:] if len(yandex_token) > 10 else ""

        return {"success": True, "yandex_token": masked, "sites": sites}
    except Exception as e:
        logger.error("Failed to get user settings for %s: %s", current_user.user_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


class UpdateSettingsRequest(BaseModel):
    yandex_token: str


@router.post("/api/user/settings")
@limiter.limit("10/minute")
async def update_user_settings(
    req: UpdateSettingsRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            cur.execute(
                "UPDATE users SET yandex_token = %s WHERE id = %s",
                (req.yandex_token, current_user.user_id),
            )
        return {"success": True}
    except Exception as e:
        logger.error("Failed to update settings for %s: %s", current_user.user_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

    @field_validator("newPassword")
    @classmethod
    def new_password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("New password must be at least 6 characters")
        return v


@router.post("/api/user/change-password")
@limiter.limit("5/minute")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        if not AuthService.change_password(
            current_user.user_id, req.currentPassword, req.newPassword
        ):
            raise HTTPException(status_code=400, detail="Неверный текущий пароль")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to change password for %s: %s", current_user.user_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")
