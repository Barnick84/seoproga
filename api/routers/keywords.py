import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user
from utils.db import get_db_cursor
from utils.helpers import extract_domain

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Keywords"])


class KeywordResponse(BaseModel):
    id: int
    query: str
    hits: int
    hits_ym: int
    hits_google: int
    minus_word: int
    clustered: int
    frequency: int
    found_url: Optional[str]


class KeywordsListResponse(BaseModel):
    keywords: List[KeywordResponse]
    count: int
    domain: str
    minus_words: List[str]


class MinusWordsRequest(BaseModel):
    domain: str
    keywords: List[str]


class ClearMinusWordsRequest(BaseModel):
    domain: str


@router.get("/api/keywords", response_model=KeywordsListResponse)
async def get_keywords(
    domain: Optional[str] = None, current_user: TokenData = Depends(get_current_user)
):
    user_id = current_user.user_id
    domain_filter = extract_domain(domain) if domain else None

    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            # Get minus words
            if domain_filter:
                cur.execute(
                    "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 1",
                    (user_id, domain_filter),
                )
            else:
                cur.execute(
                    "SELECT DISTINCT query FROM yandex_queries WHERE user_id = %s AND minus_word = 1",
                    (user_id,),
                )
            minus_words = [r["query"] for r in cur.fetchall()]

            # Get keywords
            if domain_filter:
                cur.execute(
                    """SELECT q.id, q.query, q.hits, q.hits_ym, q.hits_google, q.minus_word, q.clustered, q.frequency, h.found_url 
                       FROM yandex_queries q
                       LEFT JOIN (
                           SELECT query, user_id, site_url, found_url 
                           FROM query_history 
                           WHERE id IN (SELECT MAX(id) FROM query_history GROUP BY query, user_id, site_url)
                       ) h ON q.query = h.query AND q.user_id = h.user_id AND q.site_url = h.site_url
                       WHERE q.user_id = %s AND q.site_url = %s 
                       ORDER BY q.hits DESC""",
                    (user_id, domain_filter),
                )
            else:
                cur.execute(
                    """SELECT q.id, q.query, q.hits, q.hits_ym, q.hits_google, q.minus_word, q.clustered, q.frequency, h.found_url 
                       FROM yandex_queries q
                       LEFT JOIN (
                           SELECT query, user_id, site_url, found_url 
                           FROM query_history 
                           WHERE id IN (SELECT MAX(id) FROM query_history GROUP BY query, user_id, site_url)
                       ) h ON q.query = h.query AND q.user_id = h.user_id AND q.site_url = h.site_url
                       WHERE q.user_id = %s 
                       ORDER BY q.hits DESC""",
                    (user_id,),
                )
            rows = cur.fetchall()

            keywords = [
                KeywordResponse(
                    id=r["id"],
                    query=r["query"],
                    hits=r["hits"],
                    hits_ym=r["hits_ym"],
                    hits_google=r["hits_google"],
                    minus_word=r["minus_word"],
                    clustered=r["clustered"],
                    frequency=r["frequency"] or 0,
                    found_url=r["found_url"],
                )
                for r in rows
            ]

            return KeywordsListResponse(
                keywords=keywords,
                count=len(keywords),
                domain=domain_filter or "all",
                minus_words=minus_words,
            )
    except Exception as e:
        logger.error("Failed to fetch keywords: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/minus-words")
async def update_minus_words(
    req: MinusWordsRequest, current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(req.domain)
    if not req.keywords:
        return {"success": False, "error": "Missing parameters", "updated": 0}

    try:
        with get_db_cursor(dictionary=True, commit=True) as (conn, cur):
            placeholders = ",".join(["%s"] * len(req.keywords))
            cur.execute(
                f"UPDATE yandex_queries SET minus_word = 1 WHERE user_id = %s AND site_url = %s AND query IN ({placeholders})",
                (current_user.user_id, domain, *req.keywords),
            )
            return {"success": True, "updated": cur.rowcount}
    except Exception as e:
        logger.error("Failed to update minus words: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/restore-minus")
async def restore_minus_words(
    req: MinusWordsRequest, current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(req.domain)
    if not req.keywords:
        return {"success": False, "error": "Missing parameters", "updated": 0}

    try:
        with get_db_cursor(dictionary=True, commit=True) as (conn, cur):
            placeholders = ",".join(["%s"] * len(req.keywords))
            cur.execute(
                f"UPDATE yandex_queries SET minus_word = 0 WHERE user_id = %s AND site_url = %s AND query IN ({placeholders})",
                (current_user.user_id, domain, *req.keywords),
            )
            return {"success": True, "updated": cur.rowcount}
    except Exception as e:
        logger.error("Failed to restore minus words: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/clear-minus")
async def clear_minus_words(
    req: ClearMinusWordsRequest, current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(req.domain)
    try:
        with get_db_cursor(dictionary=True, commit=True) as (conn, cur):
            cur.execute(
                "UPDATE yandex_queries SET minus_word = 0 WHERE user_id = %s AND site_url = %s AND minus_word = 1",
                (current_user.user_id, domain),
            )
            updated = cur.rowcount
            return {"success": True, "updated": updated}
    except Exception as e:
        logger.error("Failed to clear minus words: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
