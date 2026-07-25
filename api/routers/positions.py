import asyncio
import json
import os
import sys
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from api.dependencies import get_current_user, TokenData, verify_domain_ownership
from utils.db import get_db_cursor

router = APIRouter(tags=["Positions"])


@router.get("/api/positions/clusters")
async def get_position_clusters(
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            # Get cluster IDs, mapped target URLs, and cluster names in one query
            cur.execute(
                """SELECT m.cluster_id, m.target_url, n.cluster_name
                   FROM cluster_mappings m
                   LEFT JOIN cluster_names n ON m.cluster_id = n.cluster_id AND m.user_id = n.user_id AND m.site_url = n.site_url
                   WHERE m.user_id = %s AND m.site_url = %s""",
                (current_user.user_id, domain),
            )
            rows = cur.fetchall()

        clusters = []
        for r in rows:
            clusters.append(
                {
                    "cluster_id": r["cluster_id"],
                    "target_url": r["target_url"],
                    "name": r["cluster_name"] or "",
                }
            )
        return {"success": True, "clusters": clusters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/positions/check")
async def check_positions(
    domain: str = Depends(verify_domain_ownership),
    clusterId: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        from scripts.check_positions import check_positions_task
        
        cid = int(clusterId) if clusterId else 0
        
        result = await asyncio.to_thread(
            check_positions_task,
            domain=domain,
            cluster_id=cid,
            user_id=current_user.user_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/positions/history")
async def get_positions_history(
    domain: str = Depends(verify_domain_ownership),
    engine: str = "yandex",
    device: str = "desktop",
    clusterId: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=10000),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            query = """
                SELECT q.query, qh.position, qh.engine, qh.device, qh.created_at as date
                FROM query_history qh
                JOIN yandex_queries q ON q.query = qh.query AND q.user_id = qh.user_id
                WHERE qh.user_id = %s AND qh.site_url = %s AND qh.engine = %s AND qh.device = %s
            """
            params: list = [current_user.user_id, domain, engine, device]
            if clusterId:
                query += " AND qh.cluster_id = %s"
                params.append(clusterId)
            query += " ORDER BY qh.created_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        # Group by query for the frontend format
        keywords = {}
        dates_set: set[str] = set()
        for r in rows:
            kw = r["query"]
            if kw not in keywords:
                keywords[kw] = {"query": kw, "positions": []}
            keywords[kw]["positions"].append(
                {
                    "position": r["position"],
                    "date": str(r["date"]) if r["date"] else "",
                }
            )
            if r["date"]:
                dates_set.add(str(r["date"])[:10])

        return {
            "success": True,
            "keywords": list(keywords.values()),
            "dates": sorted(dates_set, reverse=True),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def positions_streaming_process(task_func, *args):
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(msg):
        # Handle dicts for rich progress updates (like check_all_positions)
        if isinstance(msg, dict):
            payload = {"type": "progress"}
            payload.update(msg)
            loop.call_soon_threadsafe(queue.put_nowait, payload)
        else:
            # Simple string messages (like check_positions)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", "message": str(msg)})

    def wrapped_task():
        try:
            res = task_func(*args, on_progress=on_progress)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "result": res})
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})

    # Send an initial connection keepalive immediately
    yield f"data: {json.dumps({'type': 'progress', 'message': 'PROGRESS: 0', 'pct': 0, 'done': 0, 'total': 0})}\n\n"

    task = asyncio.create_task(asyncio.to_thread(wrapped_task))

    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=120)
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Process timeout'})}\n\n"
            break


@router.get("/api/positions/run-stream")
async def run_positions_stream(
    domain: str = Depends(verify_domain_ownership),
    engine: str = "yandex",
    device: str = "desktop",
    current_user: TokenData = Depends(get_current_user),
):
    from scripts.check_all_positions import check_all_positions_task
    return StreamingResponse(
        positions_streaming_process(check_all_positions_task, domain, current_user.user_id, engine, device),
        media_type="text/event-stream",
    )


@router.get("/api/cluster/check-positions-stream")
async def check_cluster_positions_stream(
    clusterId: str,
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    from scripts.check_positions import check_positions_task
    cid = int(clusterId) if clusterId else 0
    return StreamingResponse(
        positions_streaming_process(check_positions_task, domain, cid, current_user.user_id, None),
        media_type="text/event-stream",
    )


@router.post("/api/cluster/check-positions")
async def check_cluster_positions(
    clusterId: str,
    domain: str = Depends(verify_domain_ownership),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        from scripts.check_positions import check_positions_task
        
        cid = int(clusterId) if clusterId else 0
        
        result = await asyncio.to_thread(
            check_positions_task,
            domain=domain,
            cluster_id=cid,
            user_id=current_user.user_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
