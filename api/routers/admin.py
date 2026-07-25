import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.dependencies import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_admin_token
from api.main import limiter
from config import Config
from utils.db import get_db_cursor

router = APIRouter(tags=["Admin"])


class AdminLoginRequest(BaseModel):
    password: str


@router.post("/api/admin/login")
@limiter.limit("5/minute")
async def admin_login(req: AdminLoginRequest, request: Request):
    admin_password = os.environ.get("ADMIN_PASSWORD", "123456")
    if req.password == admin_password:
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"is_admin": True}, expires_delta=access_token_expires
        )
        return {"success": True, "token": access_token}
    else:
        raise HTTPException(status_code=401, detail="Неверный пароль администратора")


@router.get("/api/admin/tariffs")
@limiter.limit("20/minute")
async def get_tariffs(req: Request, admin: bool = Depends(verify_admin_token)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT `key`, `value` FROM settings")
            rows = cur.fetchall()

        settings = {r["key"]: r["value"] for r in rows}
        return {
            "success": True,
            "clustering_rate": float(settings.get("clustering_rate", 0.10)),
            "frequency_rate": float(settings.get("frequency_rate", 0.20)),
            "position_new_rate": float(settings.get("position_new_rate", 0.25)),
            "position_step_rate": float(settings.get("position_step_rate", 0.05)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateTariffsRequest(BaseModel):
    clustering_rate: float
    frequency_rate: float
    position_new_rate: float
    position_step_rate: float


@router.post("/api/admin/tariffs/update")
@limiter.limit("10/minute")
async def update_tariffs(
    req: UpdateTariffsRequest, request: Request, admin: bool = Depends(verify_admin_token)
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            queries = [
                ("clustering_rate", str(req.clustering_rate)),
                ("frequency_rate", str(req.frequency_rate)),
                ("position_new_rate", str(req.position_new_rate)),
                ("position_step_rate", str(req.position_step_rate)),
            ]

            for key, value in queries:
                cur.execute(
                    "INSERT INTO settings (`key`, `value`) VALUES (%s, %s) ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)",
                    (key, value),
                )

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/users")
@limiter.limit("20/minute")
async def get_users(request: Request, admin: bool = Depends(verify_admin_token)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT id, username, email, balance, created_at FROM users ORDER BY created_at DESC"
            )
            users = cur.fetchall()

        return {"success": True, "users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateUserRequest(BaseModel):
    id: int
    balance: float


@router.post("/api/admin/users/update")
@limiter.limit("10/minute")
async def update_user(
    req: UpdateUserRequest, request: Request, admin: bool = Depends(verify_admin_token)
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            cur.execute("UPDATE users SET balance = %s WHERE id = %s", (req.balance, req.id))

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/sites")
@limiter.limit("20/minute")
async def get_sites(request: Request, admin: bool = Depends(verify_admin_token)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT s.*, u.username FROM sites s LEFT JOIN users u ON s.user_id = u.id ORDER BY s.created_at DESC"
            )
            sites = cur.fetchall()

        return {"success": True, "sites": sites}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/payments")
@limiter.limit("20/minute")
async def get_payments(request: Request, admin: bool = Depends(verify_admin_token)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT p.*, u.username FROM payment_history p LEFT JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC"
            )
            payments = cur.fetchall()

        return {"success": True, "payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/logs")
@limiter.limit("20/minute")
async def get_logs(request: Request, admin: bool = Depends(verify_admin_token)):
    log_file = "backend.log"
    if not os.path.exists(log_file):
        return {"success": True, "logs": "No logs found."}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Read last 1000 lines or just read all
            lines = f.readlines()
            logs = "".join(lines[-1000:]) if len(lines) > 1000 else "".join(lines)

        return {"success": True, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
