import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user, verify_domain_ownership
from services.billing import BillingService, InsufficientFundsError
from utils.db import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_error_response(message: str, **extra) -> StreamingResponse:
    payload = {"type": "error", "message": message, **extra}

    async def stream():
        yield _sse_event(payload)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _enqueue_task(user_id: int, task_type: str, payload: dict) -> int:
    """Insert a task into the tasks queue for the worker daemon to pick up."""
    with get_db_cursor(commit=True, dictionary=True) as (conn, cur):
        cur.execute(
            "INSERT INTO tasks (user_id, task_type, status, progress, payload) "
            "VALUES (%s, %s, 'pending', 0, %s)",
            (user_id, task_type, json.dumps(payload, ensure_ascii=False)),
        )
        return cur.lastrowid


def _fetch_task(task_id: int) -> dict | None:
    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute("SELECT status, progress, result, error FROM tasks WHERE id = %s", (task_id,))
        return cur.fetchone()


async def _stream_task_progress(task_id: int, poll_interval: float = 2.0, timeout: float = 3600.0):
    """SSE generator that polls task progress from the DB and replays it.

    Keeps the frontend SSE contract (progress/done/error) while the actual
    work runs in the worker daemon. Emits the final result on completion.
    """
    yield _sse_event({"type": "progress", "message": "PROGRESS: 0"})
    last_progress = -1
    elapsed = 0.0
    while elapsed < timeout:
        try:
            task = await asyncio.to_thread(_fetch_task, task_id)
        except Exception as e:
            logger.exception("Failed to poll task %s", task_id)
            yield _sse_event({"type": "error", "message": f"Task status unavailable: {e}"})
            return
        if not task:
            yield _sse_event({"type": "error", "message": "Task not found"})
            return

        status = task["status"]
        progress = task["progress"] or 0
        if progress != last_progress:
            last_progress = progress
            yield _sse_event({"type": "progress", "message": f"PROGRESS: {progress}"})

        if status == "completed":
            result = task.get("result")
            result_data = json.loads(result) if isinstance(result, str) else (result or {})
            yield _sse_event({"type": "done", "result": result_data})
            return
        if status == "failed":
            yield _sse_event({"type": "error", "message": task.get("error") or "Task failed"})
            return

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    yield _sse_event({"type": "error", "message": "Task timed out"})


def get_system_settings(cur) -> dict:
    try:
        cur.execute("SELECT `key`, `value` FROM settings")
        rows = cur.fetchall()
        settings = {r["key"]: r["value"] for r in rows}
        return {
            "clustering_rate": float(settings.get("clustering_rate", 0.10)),
            "frequency_rate": float(settings.get("frequency_rate", 0.20)),
            "position_new_rate": float(settings.get("position_new_rate", 0.25)),
            "position_step_rate": float(settings.get("position_step_rate", 0.05)),
        }
    except Exception as e:
        logger.error("Failed to fetch system settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load system billing settings.")


@router.get("/api/run-clustering-stream")
async def run_clustering_stream(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            settings = get_system_settings(cur)

            cur.execute(
                "SELECT COUNT(*) as count FROM yandex_queries WHERE user_id = %s AND site_url = %s AND minus_word = 0 AND clustered = 0",
                (current_user.user_id, domain),
            )
            row = cur.fetchone()
            kw_count = row["count"]

            if kw_count > 0:
                cost = kw_count * settings["clustering_rate"]
                try:
                    BillingService.deduct_balance(
                        current_user.user_id,
                        cost,
                        f"Кластеризация {kw_count} запросов ({domain})",
                        operation_type="charge",
                    )
                except InsufficientFundsError as e:
                    return _sse_error_response(e.to_dict()["message"], **e.to_dict())
                except ValueError as e:
                    return _sse_error_response(str(e))

        task_id = _enqueue_task(
            current_user.user_id,
            "clustering",
            {"domain": domain, "user_id": current_user.user_id},
        )
    except HTTPException:
        raise
    except Exception as exc:
        return _sse_error_response(str(exc))

    return StreamingResponse(_stream_task_progress(task_id), media_type="text/event-stream")


@router.get("/api/run-mapping-stream")
async def run_mapping_stream(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        task_id = _enqueue_task(
            current_user.user_id,
            "mapping",
            {"domain": domain, "user_id": current_user.user_id},
        )
    except Exception as exc:
        return _sse_error_response(str(exc))

    return StreamingResponse(_stream_task_progress(task_id), media_type="text/event-stream")


class MappingRequest(BaseModel):
    domain: str


@router.post("/api/run-mapping")
async def run_mapping(req: MappingRequest, current_user: TokenData = Depends(get_current_user)):
    # req.domain doesn't use Depends() because it's in body, so we manually verify it
    from utils.helpers import extract_domain

    domain = extract_domain(req.domain)
    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "SELECT 1 FROM sites WHERE user_id = %s AND domain = %s", (current_user.user_id, domain)
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=403, detail="Forbidden: You do not have access to this domain."
            )

    try:
        task_id = _enqueue_task(
            current_user.user_id,
            "mapping",
            {"domain": domain, "user_id": current_user.user_id},
        )
        return {"success": True, "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "run_mapping failed for user_id=%s domain=%s", current_user.user_id, domain
        )
        return {"success": False, "error": str(e)}


@router.get("/api/analysis-status")
async def get_analysis_status(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute(
            "SELECT id FROM tasks WHERE user_id = %s AND task_type = 'competitor_analysis' "
            "AND status IN ('pending', 'scheduled', 'running') "
            "ORDER BY id DESC LIMIT 1",
            (current_user.user_id,),
        )
        return {"running": cur.fetchone() is not None}


@router.get("/api/run-competitor-analysis-stream")
async def run_competitor_analysis_stream(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        task_id = _enqueue_task(
            current_user.user_id,
            "competitor_analysis",
            {"domain": domain, "user_id": current_user.user_id},
        )
        return {"success": True, "task_id": task_id}
    except Exception as e:
        logger.exception(
            "run_competitor_analysis failed for user_id=%s domain=%s",
            current_user.user_id,
            domain,
        )
        return {"success": False, "error": str(e)}


@router.get("/api/run-frequency-stream")
async def run_frequency_stream(
    domain: str = Depends(verify_domain_ownership),
    region: str = "225",
    clusterId: str = "",
    mode: str = "all",
    minFrequency: int = 10,
    device: str = "",
    current_user: TokenData = Depends(get_current_user),
):
    try:
        cluster_id_int = int(clusterId) if clusterId else 0
        task_id = _enqueue_task(
            current_user.user_id,
            "frequency",
            {
                "domain": domain,
                "user_id": current_user.user_id,
                "device": device,
                "region": region,
                "mode": mode,
                "minFrequency": minFrequency,
                "clusterId": cluster_id_int,
            },
        )
        return {"success": True, "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "run_frequency failed for user_id=%s domain=%s", current_user.user_id, domain
        )
        return {"success": False, "error": str(e)}


@router.get("/api/tasks/{task_id}")
async def get_task_status(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at FROM tasks WHERE id = %s AND user_id = %s",
                (task_id, current_user.user_id),
            )
            task = cur.fetchone()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            return {"success": True, "task": task}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error("Failed to get task status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/frequency-task-status")
async def get_frequency_task_status(
    taskId: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at FROM tasks WHERE id = %s AND user_id = %s",
                (taskId, current_user.user_id),
            )
            task = cur.fetchone()
            if not task:
                return {"success": False, "error": "Task not found"}
            return {"success": True, "task": task}
    except Exception as e:
        logger.error("Failed to get frequency task status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


class FullPipelineRequest(BaseModel):
    domain: str
    clusterId: str
    targetUrl: str
    region: Optional[str] = "213"
    headQuery: Optional[str] = None


@router.post("/api/run-full-pipeline")
async def run_full_pipeline(
    req: FullPipelineRequest,
    current_user: TokenData = Depends(get_current_user),
):
    from utils.helpers import extract_domain

    domain = extract_domain(req.domain)
    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "SELECT 1 FROM sites WHERE user_id = %s AND domain = %s", (current_user.user_id, domain)
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=403, detail="Forbidden: You do not have access to this domain."
            )

    payload = json.dumps(
        {
            "domain": domain,
            "cluster_id": req.clusterId,
            "target_url": req.targetUrl,
            "region": req.region,
            "head_query": req.headQuery,
        },
        ensure_ascii=False,
    )

    try:
        with get_db_cursor() as (conn, cur):
            cur.execute(
                "INSERT INTO tasks (user_id, task_type, status, progress, payload) VALUES (%s, 'seo_pipeline', 'pending', 0, %s)",
                (current_user.user_id, payload),
            )
            task_id = cur.lastrowid
            conn.commit()
        return {"success": True, "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "run_full_pipeline failed for user_id=%s domain=%s", current_user.user_id, domain
        )
        return {"success": False, "error": str(e)}


@router.get("/api/active-pipeline-status")
async def get_active_pipeline_status(
    domain: str,
    clusterId: str,
    current_user: TokenData = Depends(get_current_user),
):
    from utils.helpers import extract_domain

    clean_domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                """
                SELECT id, task_type, status, progress, payload, result, error, created_at, started_at, finished_at
                FROM tasks
                WHERE user_id = %s AND task_type = 'seo_pipeline' AND status IN ('pending', 'scheduled', 'running')
                ORDER BY id DESC LIMIT 1
                """,
                (current_user.user_id,),
            )
            rows = cur.fetchall()
            for task in rows:
                p = task["payload"]
                if isinstance(p, str):
                    p = json.loads(p)
                if (
                    p
                    and str(p.get("domain", "")).lower() == clean_domain.lower()
                    and str(p.get("cluster_id", p.get("clusterId", ""))) == str(clusterId)
                ):
                    return {"success": True, "task": task}
            return {"success": True, "task": None}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "get_active_pipeline_status failed for user_id=%s domain=%s",
            current_user.user_id,
            clean_domain,
        )
        return {"success": False, "error": str(e)}
