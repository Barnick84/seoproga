import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user, verify_domain_ownership
from utils.db import get_db_cursor

router = APIRouter(tags=["Analysis"])

# In-memory tracking of running analysis processes (user_id:domain -> bool)
running_analyses = set()


async def run_streaming_process(task_func, *args):
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(msg: str):
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", "message": msg})

    def wrapped_task():
        try:
            res = task_func(*args, on_progress=on_progress)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "result": res})
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})

    # Send an initial connection keepalive immediately
    yield f"data: {json.dumps({'type': 'progress', 'message': 'PROGRESS: 0'})}\n\n"

    task = asyncio.create_task(asyncio.to_thread(wrapped_task))

    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=120)
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Process timeout or inactivity'})}\n\n"
            break

    # ensure task finishes/cleanup if possible, though it's a background thread
    if not task.done():
        pass


def get_system_settings(cur):
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
        import logging

        logging.error(f"Failed to fetch system settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to load system billing settings.")


def check_and_deduct_balance(conn, cur, user_id, amount, description):
    try:
        conn.start_transaction()
        cur.execute(
            "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
            (amount, user_id, amount),
        )

        if cur.rowcount == 0:
            cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found")
            balance = float(row["balance"])
            raise ValueError(
                json.dumps(
                    {
                        "error": "INSUFFICIENT_FUNDS",
                        "message": f"Недостаточно средств. Требуется: {amount:.2f} ₽, доступно: {balance:.2f} ₽",
                        "required": amount,
                        "available": balance,
                        "missing": amount - balance,
                    }
                )
            )

        cur.execute(
            "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
            (user_id, amount, description, "charge"),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


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
                    check_and_deduct_balance(
                        conn,
                        cur,
                        current_user.user_id,
                        cost,
                        f"Кластеризация {kw_count} запросов ({domain})",
                    )
                except ValueError as e:
                    err_msg = str(e)
                    if "INSUFFICIENT_FUNDS" in err_msg:
                        err_data = json.loads(err_msg)

                        async def stream_insufficient():
                            yield f"data: {json.dumps({'type': 'error', **err_data})}\n\n"

                        return StreamingResponse(
                            stream_insufficient(), media_type="text/event-stream"
                        )
                    else:

                        async def stream_err():
                            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"

                        return StreamingResponse(stream_err(), media_type="text/event-stream")

    except Exception:

        async def stream_err2():
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(stream_err2(), media_type="text/event-stream")

    # We will yield events using StreamingResponse
    from scripts.run_clustering import run_clustering_task

    return StreamingResponse(
        run_streaming_process(run_clustering_task, domain, current_user.user_id, 0),
        media_type="text/event-stream",
    )


@router.get("/api/run-mapping-stream")
async def run_mapping_stream(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    from scripts.run_mapping import run_mapping_task

    return StreamingResponse(
        run_streaming_process(run_mapping_task, domain, current_user.user_id, None, 0),
        media_type="text/event-stream",
    )


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

    from scripts.run_mapping import run_mapping_task

    try:
        result = await asyncio.to_thread(run_mapping_task, domain, current_user.user_id, None, 0)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/analysis-status")
async def get_analysis_status(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    analysis_key = f"{current_user.user_id}:{domain}"
    return {"running": analysis_key in running_analyses}


@router.get("/api/run-competitor-analysis-stream")
async def run_competitor_analysis_stream(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    analysis_key = f"{current_user.user_id}:{domain}"

    if analysis_key in running_analyses:
        raise HTTPException(status_code=409, detail="Analysis already running for this domain")

    running_analyses.add(analysis_key)

    def wrapped_task():
        from scripts.run_competitor_analysis import run_competitor_analysis_task

        try:
            run_competitor_analysis_task(domain, current_user.user_id)
        finally:
            running_analyses.discard(analysis_key)

    asyncio.create_task(asyncio.to_thread(wrapped_task))
    return {"success": True, "message": "Analysis started"}


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

        with get_db_cursor() as (conn, cur):
            cur.execute(
                "INSERT INTO tasks (user_id, task_type, status, created_at, started_at) VALUES (%s, %s, 'running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (current_user.user_id, "frequency"),
            )
            task_id = cur.lastrowid
            conn.commit()

        def wrapped_task():
            from scripts.fetch_frequency import fetch_frequency_task

            fetch_frequency_task(
                domain=domain,
                user_id=current_user.user_id,
                device=device,
                region=region,
                mode=mode,
                min_freq=minFrequency,
                task_id=task_id,
                cluster_id=cluster_id_int,
            )

        asyncio.create_task(asyncio.to_thread(wrapped_task))
        return {"success": True, "task_id": task_id}
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
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
    except Exception as e:
        return {"success": False, "error": str(e)}
