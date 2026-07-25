from fastapi import APIRouter

from utils.db import get_db_cursor

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """Readiness check endpoint that verifies DB connectivity."""
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ready"}
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Database connection failed")
