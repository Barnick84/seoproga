import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user, verify_domain_ownership
from config import Config
from utils.db import get_db_cursor
from utils.helpers import extract_domain

router = APIRouter(tags=["Cluster"])


# --- Models ---


class DomainRequest(BaseModel):
    domain: str


class TargetUrlRequest(BaseModel):
    domain: str
    clusterId: str
    target_url: str


class ClusterIdRequest(BaseModel):
    domain: str
    clusterId: str


class ClusterNameRequest(BaseModel):
    domain: str
    clusterId: str
    name: str


class ToggleRequest(BaseModel):
    domain: str
    clusterId: str


class PinnedOrderRequest(BaseModel):
    domain: str
    order: dict[str, int]


class MappingManualRequest(BaseModel):
    domain: str
    clusterId: str
    target_url: str


class UpdateKeywordTextRequest(BaseModel):
    domain: str
    clusterId: str
    oldKeyword: str
    newKeyword: str


class CreateClusterByUrlRequest(BaseModel):
    domain: str
    url: str


class CollectKeywordsRequest(BaseModel):
    domain: str
    clusterId: str


class RunSeoAnalysisRequest(BaseModel):
    domain: str
    clusterId: str


class GenerateStructureRequest(BaseModel):
    domain: str
    clusterId: str
    keywords: list[str]


class SaveStructureRequest(BaseModel):
    domain: str
    clusterId: str
    structure: str


class RemoveLsiRequest(BaseModel):
    domain: str
    clusterId: str
    keyword: str


class SeoHistoryGenerateRequest(BaseModel):
    domain: str
    clusterId: str
    seo_plan: str


# --- Helpers ---


def _get_settings(cur):
    try:
        cur.execute("SELECT `key`, `value` FROM settings")
        rows = cur.fetchall()
        return {r["key"]: r["value"] for r in rows}
    except Exception:
        return {}


# --- Mappings ---


@router.get("/api/mappings")
async def get_mappings(
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT cluster_id, target_url FROM cluster_mappings WHERE user_id = %s AND site_url = %s",
                (current_user.user_id, domain),
            )
            rows = cur.fetchall()
            mappings = {r["cluster_id"]: r["target_url"] for r in rows}
            return {"success": True, "mappings": mappings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/save-mapping-manual")
async def save_mapping_manual(
    req: MappingManualRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

        cur.execute(
            "SELECT 1 FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE cluster_mappings SET target_url = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (req.target_url, current_user.user_id, domain, req.clusterId),
            )
        else:
            cur.execute(
                "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (%s, %s, %s, %s)",
                (current_user.user_id, domain, req.clusterId, req.target_url),
            )
        return {"success": True}


@router.post("/api/cluster/target-url")
async def set_cluster_target_url(
    req: TargetUrlRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "SELECT 1 FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE cluster_mappings SET target_url = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (req.target_url, current_user.user_id, domain, req.clusterId),
            )
        else:
            cur.execute(
                "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (%s, %s, %s, %s)",
                (current_user.user_id, domain, req.clusterId, req.target_url),
            )
        return {"success": True}


# --- Cluster Analysis ---


@router.get("/api/analysis")
async def get_cluster_analysis(
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT cluster_id, analysis_data FROM cluster_analysis WHERE user_id = %s AND site_url = %s",
                (current_user.user_id, domain),
            )
            rows = cur.fetchall()
            analysis = {}
            for r in rows:
                try:
                    analysis[r["cluster_id"]] = (
                        json.loads(r["analysis_data"])
                        if isinstance(r["analysis_data"], str)
                        else r["analysis_data"]
                    )
                except (json.JSONDecodeError, TypeError):
                    analysis[r["cluster_id"]] = r["analysis_data"]
            return {"success": True, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cluster/run-seo-analysis")
async def run_cluster_seo_analysis(
    req: RunSeoAnalysisRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    from scripts.run_seo_analysis import run_seo_analysis_task

    try:
        result = await asyncio.to_thread(
            run_seo_analysis_task, domain, int(req.clusterId), current_user.user_id
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Cluster Names / Metadata ---


@router.get("/api/cluster-names")
async def get_cluster_names(
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                """SELECT cluster_id, cluster_name, is_favorite, is_pinned, pinned_order
                   FROM cluster_names WHERE user_id = %s AND site_url = %s""",
                (current_user.user_id, domain),
            )
            rows = cur.fetchall()
            names = {}
            for r in rows:
                names[r["cluster_id"]] = {
                    "name": r["cluster_name"] or "",
                    "is_favorite": bool(r["is_favorite"]),
                    "is_pinned": bool(r["is_pinned"]),
                    "pinned_order": r["pinned_order"] or 0,
                }
            return {"success": True, "names": names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/update-cluster-name")
async def update_cluster_name(
    req: ClusterNameRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "SELECT 1 FROM cluster_names WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE cluster_names SET cluster_name = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (req.name, current_user.user_id, domain, req.clusterId),
            )
        else:
            cur.execute(
                "INSERT INTO cluster_names (user_id, site_url, cluster_id, cluster_name) VALUES (%s, %s, %s, %s)",
                (current_user.user_id, domain, req.clusterId, req.name),
            )
        return {"success": True}


@router.post("/api/toggle-cluster-favorite")
async def toggle_cluster_favorite(
    req: ToggleRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute(
            "SELECT is_favorite FROM cluster_names WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        row = cur.fetchone()
        new_val = 0 if (row and row["is_favorite"]) else 1
        if row is not None:
            cur.execute(
                "UPDATE cluster_names SET is_favorite = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (new_val, current_user.user_id, domain, req.clusterId),
            )
        else:
            cur.execute(
                "INSERT INTO cluster_names (user_id, site_url, cluster_id, is_favorite) VALUES (%s, %s, %s, %s)",
                (current_user.user_id, domain, req.clusterId, new_val),
            )
        return {"success": True, "is_favorite": bool(new_val)}


@router.post("/api/toggle-cluster-pinned")
async def toggle_cluster_pinned(
    req: ToggleRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute(
            "SELECT is_pinned FROM cluster_names WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        row = cur.fetchone()
        new_val = 0 if (row and row["is_pinned"]) else 1
        if row is not None:
            cur.execute(
                "UPDATE cluster_names SET is_pinned = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (new_val, current_user.user_id, domain, req.clusterId),
            )
        else:
            cur.execute(
                "INSERT INTO cluster_names (user_id, site_url, cluster_id, is_pinned) VALUES (%s, %s, %s, %s)",
                (current_user.user_id, domain, req.clusterId, new_val),
            )
        return {"success": True, "is_pinned": bool(new_val)}


@router.post("/api/update-pinned-order")
async def update_pinned_order(
    req: PinnedOrderRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        for cluster_id, order in req.order.items():
            cur.execute(
                "SELECT 1 FROM cluster_names WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                (current_user.user_id, domain, cluster_id),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE cluster_names SET pinned_order = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                    (order, current_user.user_id, domain, cluster_id),
                )
            else:
                cur.execute(
                    "INSERT INTO cluster_names (user_id, site_url, cluster_id, pinned_order) VALUES (%s, %s, %s, %s)",
                    (current_user.user_id, domain, cluster_id, order),
                )
        return {"success": True}


# --- Cluster LSI ---


@router.get("/api/cluster-lsi")
async def get_cluster_lsi(
    clusterId: str,
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT keyword, frequency FROM cluster_lsi WHERE user_id = %s AND site_url = %s AND cluster_id = %s ORDER BY frequency DESC",
                (current_user.user_id, domain, clusterId),
            )
            rows = cur.fetchall()
            return {"success": True, "keywords": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cluster/remove-lsi")
async def remove_cluster_lsi(
    req: RemoveLsiRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "DELETE FROM cluster_lsi WHERE user_id = %s AND site_url = %s AND cluster_id = %s AND keyword = %s",
            (current_user.user_id, domain, req.clusterId, req.keyword),
        )
        return {"success": True}


# --- Cluster management ---


@router.post("/api/disband-cluster")
async def disband_cluster(
    req: ClusterIdRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "DELETE FROM cluster_analysis WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        cur.execute(
            "DELETE FROM cluster_mappings WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        cur.execute(
            "DELETE FROM cluster_names WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        cur.execute(
            "DELETE FROM cluster_lsi WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        cur.execute(
            "DELETE FROM cluster_seo_history WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
            (current_user.user_id, domain, req.clusterId),
        )
        return {"success": True}


@router.post("/api/update-keyword-text")
async def update_keyword_text(
    req: UpdateKeywordTextRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            "UPDATE yandex_queries SET query = %s WHERE user_id = %s AND site_url = %s AND query = %s",
            (req.newKeyword, current_user.user_id, domain, req.oldKeyword),
        )
        return {"success": True, "updated": cur.rowcount}


@router.post("/api/create-cluster-by-url")
async def create_cluster_by_url(
    req: CreateClusterByUrlRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    from scripts.create_cluster_from_url import create_cluster_from_url_task

    try:
        result = await asyncio.to_thread(
            create_cluster_from_url_task, domain, current_user.user_id, req.url
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/collect-keywords-for-cluster")
async def collect_keywords_for_cluster(
    req: CollectKeywordsRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    from scripts.collect_cluster_keywords import collect_cluster_keywords_task

    try:
        result = await asyncio.to_thread(
            collect_cluster_keywords_task,
            domain,
            current_user.user_id,
            int(req.clusterId),
            head_query=None,
            source_type="popular",
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- SEO History ---


@router.get("/api/seo-history/dates")
async def get_seo_history_dates(
    clusterId: str,
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                """SELECT DISTINCT DATE(analysis_date) as date
                   FROM cluster_seo_history
                   WHERE user_id = %s AND site_url = %s AND cluster_id = %s
                   ORDER BY date DESC""",
                (current_user.user_id, domain, clusterId),
            )
            rows = cur.fetchall()
            dates = [str(r["date"]) for r in rows]
            return {"success": True, "dates": dates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/seo-history/plan")
async def get_seo_history_plan(
    clusterId: str,
    date: str,
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                """SELECT * FROM cluster_seo_history
                   WHERE user_id = %s AND site_url = %s AND cluster_id = %s AND DATE(analysis_date) = %s
                   ORDER BY analysis_date DESC LIMIT 1""",
                (current_user.user_id, domain, clusterId, date),
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": "No history found"}
            return {"success": True, "history": row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/seo-history/generate")
async def generate_seo_history(
    req: SeoHistoryGenerateRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    from scripts.generate_seo_plan import generate_seo_plan

    try:
        result = await asyncio.to_thread(
            generate_seo_plan, domain, req.clusterId, current_user.user_id, req.seo_plan
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Structure ---


@router.post("/api/cluster/generate-structure")
async def generate_cluster_structure(
    req: GenerateStructureRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    from scripts.generate_structure import generate_structure_task

    try:
        result = await asyncio.to_thread(
            generate_structure_task, domain, current_user.user_id, int(req.clusterId), req.keywords
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/cluster/save-structure")
async def save_cluster_structure(
    req: SaveStructureRequest, current_user: TokenData = Depends(get_current_user)
):
    from fastapi import HTTPException

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

    with get_db_cursor(dictionary=False) as (conn, cur):
        cur.execute(
            """INSERT INTO cluster_seo_history (user_id, site_url, cluster_id, seo_plan_content)
               VALUES (%s, %s, %s, %s)""",
            (current_user.user_id, domain, req.clusterId, req.structure),
        )
        return {"success": True}


# --- Yandex Webmaster helpers ---


@router.get("/api/fetch-wm-queries")
async def fetch_wm_queries(
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    from scripts.fetch_yandex_queries import fetch_yandex_queries_task

    try:
        result = await asyncio.to_thread(fetch_yandex_queries_task, domain, current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/get-wm-hosts")
async def get_wm_hosts(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute("SELECT yandex_token FROM users WHERE id = %s", (current_user.user_id,))
            row = cur.fetchone()
            token = row["yandex_token"] if row and row["yandex_token"] else Config.YANDEX_TOKEN
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not token:
        return {"success": False, "error": "Yandex token not found"}

    try:
        from services.yandex_webmaster import YandexWebmasterClient

        client = YandexWebmasterClient(token, current_user.user_id)
        hosts = client.list_hosts()
        return {"success": True, "hosts": hosts}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Competitor Analysis Single ---


@router.get("/api/run-competitor-analysis-single")
async def run_competitor_analysis_single(
    clusterId: str,
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    from scripts.run_competitor_analysis import run_competitor_analysis_task

    try:
        result = await asyncio.to_thread(
            run_competitor_analysis_task, domain, current_user.user_id, int(clusterId), 0
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Run clustering (non-streaming) ---


@router.get("/api/run-clustering")
async def run_clustering(
    current_user: TokenData = Depends(get_current_user),
    domain: str = Depends(verify_domain_ownership),
):
    domain = extract_domain(domain)
    from scripts.run_clustering import run_clustering_task

    try:
        result = await asyncio.to_thread(run_clustering_task, domain, current_user.user_id, 0)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MoveKeywordsRequest(BaseModel):
    domain: str
    keywords: list[str]
    target: str


@router.post("/api/move-keywords")
async def move_keywords(
    req: MoveKeywordsRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if not req.domain or not req.keywords or not req.target:
        raise HTTPException(status_code=400, detail="Domain, keywords and target required")

    normalized_domain = extract_domain(req.domain)
    target_cluster = 0 if req.target == "unclustered" else int(req.target)

    placeholders = ",".join(["%s"] * len(req.keywords))
    with get_db_cursor(commit=True) as (conn, cur):
        if target_cluster == 0:
            cur.execute(
                f"UPDATE yandex_queries SET clustered = 0 WHERE user_id = %s AND site_url = %s AND query IN ({placeholders})",
                [current_user.user_id, normalized_domain, *req.keywords],
            )
        else:
            cur.execute(
                f"UPDATE yandex_queries SET clustered = %s WHERE user_id = %s AND site_url = %s AND query IN ({placeholders})",
                [target_cluster, current_user.user_id, normalized_domain, *req.keywords],
            )

    return {"success": True, "moved": len(req.keywords)}


class DeleteClusterRequest(BaseModel):
    domain: str
    clusterId: int


@router.post("/api/delete-cluster")
async def delete_cluster(
    req: DeleteClusterRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if not req.domain or not req.clusterId:
        raise HTTPException(status_code=400, detail="Domain and clusterId required")

    normalized_domain = extract_domain(req.domain)

    with get_db_cursor(commit=True) as (conn, cur):
        cur.execute(
            "UPDATE yandex_queries SET clustered = 0 WHERE user_id = %s AND site_url = %s AND clustered = %s",
            (current_user.user_id, normalized_domain, req.clusterId),
        )
        moved = cur.rowcount

    return {"success": True, "moved": moved}
