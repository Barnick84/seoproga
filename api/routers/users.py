from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from api.dependencies import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    SECRET_KEY,
    TokenData,
    create_access_token,
    get_current_user,
    revoke_token,
)
from api.main import limiter
from services.auth import AuthService
from utils.db import get_db_cursor

router = APIRouter(tags=["Users"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""
    yandex_token: Optional[str] = ""


class TokenResponse(BaseModel):
    success: bool
    session: str  # Token
    user_id: int
    username: str
    tokens: Optional[dict] = None  # Original tokens from Node.js format


class UserInfoResponse(BaseModel):
    success: bool
    user: dict


@router.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register(req: RegisterRequest, request: Request):
    try:
        # ensure email is not None
        email = req.email if req.email else ""
        user_id = AuthService.register_user(req.username, email, req.password)
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"user_id": user_id, "username": req.username}, expires_delta=access_token_expires
        )
        return TokenResponse(
            success=True, session=access_token, user_id=user_id, username=req.username
        )
    except Exception as e:
        if "Duplicate entry" in str(e):
            raise HTTPException(status_code=400, detail="Username or email already exists")
        raise HTTPException(status_code=500, detail=str(e))


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
async def get_session(current_user: TokenData = Depends(get_current_user)):
    return {"success": True, "user_id": current_user.user_id, "username": current_user.username}


@router.post("/api/auth/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    authorization: str | None = Header(None),
):
    if authorization and current_user.jti:
        try:
            import jwt as pyjwt

            parts = authorization.split()
            token_str = parts[1] if len(parts) == 2 else authorization
            payload = pyjwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
            exp = payload.get("exp", 0)
        except Exception:
            exp = 0
        revoke_token(current_user.jti, exp)
    return {"success": True, "message": "Logged out"}


@router.get("/api/user-info", response_model=UserInfoResponse)
async def get_user_info(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT username, balance FROM users WHERE id = %s", (current_user.user_id,)
            )
            user = cur.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserInfoResponse(success=True, user=user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/user/settings")
async def get_user_settings(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT yandex_token FROM users WHERE id = %s", (current_user.user_id,))
            user_row = cur.fetchone()

            cur.execute("SELECT domain FROM sites WHERE user_id = %s", (current_user.user_id,))
            sites = [row["domain"] for row in cur.fetchall()]

        yandex_token = user_row["yandex_token"] if user_row and user_row["yandex_token"] else ""

        return {"success": True, "yandex_token": yandex_token, "sites": sites}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateSettingsRequest(BaseModel):
    yandex_token: str


@router.post("/api/user/settings")
async def update_user_settings(
    req: UpdateSettingsRequest, current_user: TokenData = Depends(get_current_user)
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            cur.execute(
                "UPDATE users SET yandex_token = %s WHERE id = %s",
                (req.yandex_token, current_user.user_id),
            )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


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
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))
