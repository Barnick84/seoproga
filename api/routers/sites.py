import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user
from services.yandex_webmaster import YandexWebmasterClient
from utils.db import get_db_cursor
from utils.helpers import extract_domain

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sites"])


class SiteDomainRequest(BaseModel):
    domain: str


class SiteResponse(BaseModel):
    id: int
    domain: str
    created_at: str


class SitesListResponse(BaseModel):
    sites: List[SiteResponse]
    count: int


@router.get("/api/sites", response_model=SitesListResponse)
async def get_sites(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT id, domain, created_at FROM sites WHERE user_id = %s ORDER BY created_at DESC",
                (current_user.user_id,),
            )
            rows = cur.fetchall()
            sites = [
                SiteResponse(id=r["id"], domain=r["domain"], created_at=str(r["created_at"]))
                for r in rows
            ]
            return SitesListResponse(sites=sites, count=len(sites))
    except Exception as e:
        logger.error("Failed to fetch sites: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/check-domain")
async def check_domain(req: SiteDomainRequest, current_user: TokenData = Depends(get_current_user)):
    domain = extract_domain(req.domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT yandex_token FROM users WHERE id = %s", (current_user.user_id,))
            row = cur.fetchone()
            token = row["yandex_token"] if row else ""
    except Exception as e:
        logger.error("Failed to fetch yandex token: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

    if not token:
        return {"linked": False, "error": "Add your Yandex token in settings first"}

    try:
        client = YandexWebmasterClient(token, current_user.user_id)
        y_user_id = client._get_user_id()
        host_id = client._get_host_id(domain, y_user_id)
        return {"linked": True, "host_id": host_id}
    except Exception as e:
        return {"linked": False, "error": str(e)}


@router.post("/api/sites")
async def add_site(req: SiteDomainRequest, current_user: TokenData = Depends(get_current_user)):
    domain = extract_domain(req.domain)

    # 1. Check if domain already owned by another user
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT user_id FROM sites WHERE domain = %s", (domain,))
            row = cur.fetchone()
            if row and row["user_id"] and row["user_id"] != current_user.user_id:
                return {
                    "success": False,
                    "message": "Этот сайт уже привязан к другому пользователю",
                }
    except Exception as e:
        logger.error("Failed to check domain ownership: %s", e)

    # 2. Check if domain is linked to WM
    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute("SELECT yandex_token FROM users WHERE id = %s", (current_user.user_id,))
        row = cur.fetchone()
        token = row["yandex_token"] if row and row["yandex_token"] else ""

    if not token:
        return {"success": False, "message": "Add your Yandex token in settings first"}

    try:
        client = YandexWebmasterClient(token, current_user.user_id)
        y_user_id = client._get_user_id()
        host_id = client._get_host_id(domain, y_user_id)
    except Exception:
        return {
            "success": False,
            "message": "Домен не привязан к вашему аккаунту Яндекс.Вебмастера",
        }

    # 3. Add to sites DB
    try:
        with get_db_cursor(dictionary=True, commit=True) as (conn, cur):
            cur.execute(
                "SELECT id FROM sites WHERE domain = %s AND user_id = %s",
                (domain, current_user.user_id),
            )
            if cur.fetchone():
                return {"success": False, "error": "Сайт уже добавлен в ваш кабинет"}

            cur.execute(
                "INSERT INTO sites (domain, user_id) VALUES (%s, %s)",
                (domain, current_user.user_id),
            )
            site_id = cur.lastrowid
            return {"success": True, "id": site_id, "domain": domain}
    except Exception as e:
        logger.error("Failed to add site: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
