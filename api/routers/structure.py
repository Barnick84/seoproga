# api/routers/structure.py
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from api.dependencies import TokenData, get_current_user
from config import Config
from utils.db import get_db_cursor
from utils.helpers import extract_domain

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Structure"])


# --- Models ---

class SaveStructureRequest(BaseModel):
    site_url: str
    structure: List[Dict[str, Any]]


class GenerateStructureRequest(BaseModel):
    site_url: str
    mode: Optional[str] = "auto"  # "auto" or "incremental"


class PageTypeCreateRequest(BaseModel):
    name: str
    icon: Optional[str] = "fa-file"
    color: Optional[str] = "#3b82f6"
    template_description: Optional[str] = ""


class PageTypeUpdateRequest(BaseModel):
    name: str
    icon: Optional[str] = "fa-file"
    color: Optional[str] = "#3b82f6"
    template_description: Optional[str] = ""


# --- Endpoints ---

@router.get("/api/site-structure")
async def get_site_structure(
    site_url: str,
    current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(site_url)
    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute(
            "SELECT structure_json, updated_at FROM site_structure WHERE user_id = %s AND site_url = %s",
            (current_user.user_id, domain)
        )
        row = cur.fetchone()
        if not row:
            return {"exists": False, "structure": []}
        
        try:
            struct_data = json.loads(row["structure_json"])
        except Exception:
            struct_data = []

        return {
            "exists": True,
            "structure": struct_data,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None
        }


@router.post("/api/site-structure/save")
async def save_site_structure(
    req: SaveStructureRequest,
    current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(req.site_url)
    json_str = json.dumps(req.structure, ensure_ascii=False)
    
    with get_db_cursor(commit=True) as (conn, cur):
        if Config.DB_TYPE == "postgresql":
            cur.execute(
                """
                INSERT INTO site_structure (user_id, site_url, structure_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, site_url) DO UPDATE SET structure_json = EXCLUDED.structure_json, updated_at = NOW()
                """,
                (current_user.user_id, domain, json_str)
            )
        else:
            cur.execute(
                """
                INSERT INTO site_structure (user_id, site_url, structure_json)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE structure_json = VALUES(structure_json)
                """,
                (current_user.user_id, domain, json_str)
            )

    return {"success": True, "message": "Структура сайта успешно сохранена"}


@router.post("/api/site-structure/generate")
async def generate_site_structure(
    req: GenerateStructureRequest,
    current_user: TokenData = Depends(get_current_user)
):
    domain = extract_domain(req.site_url)

    # 1. Fetch clusters and mapped URLs for the site
    clusters = []
    existing_structure = []
    
    with get_db_cursor(dictionary=True) as (conn, cur):
        # Fetch clusters
        cur.execute(
            """
            SELECT q.clustered as cluster_id, MIN(q.query) as main_kw, COUNT(*) as kw_count,
                   n.cluster_name, m.target_url
            FROM yandex_queries q
            LEFT JOIN cluster_names n ON q.clustered = CAST(n.cluster_id AS CHAR) AND q.user_id = n.user_id AND q.site_url = n.site_url
            LEFT JOIN cluster_mappings m ON q.clustered = CAST(m.cluster_id AS CHAR) AND q.user_id = m.user_id AND q.site_url = m.site_url
            WHERE q.user_id = %s AND q.site_url = %s AND q.minus_word = 0 AND q.clustered > 0
            GROUP BY q.clustered, n.cluster_name, m.target_url
            """,
            (current_user.user_id, domain)
        )
        cluster_rows = cur.fetchall()

        for r in cluster_rows:
            cid = str(r["cluster_id"])
            name = r["cluster_name"] or r["main_kw"]
            target_url = r["target_url"] or ""
            clusters.append({
                "cluster_id": cid,
                "name": name,
                "target_url": target_url,
                "keywords_count": r["kw_count"]
            })

        # Fetch existing structure if mode is incremental
        if req.mode == "incremental":
            cur.execute(
                "SELECT structure_json FROM site_structure WHERE user_id = %s AND site_url = %s",
                (current_user.user_id, domain)
            )
            ex_row = cur.fetchone()
            if ex_row and ex_row.get("structure_json"):
                try:
                    existing_structure = json.loads(ex_row["structure_json"])
                except Exception:
                    existing_structure = []

    if not clusters:
        raise HTTPException(status_code=400, detail="На сайте отсутствуют кластеры запросов. Сначала выполните кластеризацию.")

    # Build LLM Prompt
    system_prompt = """Ты senior SEO-архитектор. Твоя задача — построить идеальную структуру сайта на основе поисковых кластеров.
Возвращай ТОЛЬКО валидный JSON без markdown-обёрток и комментариев.

Формат узлов структуры:
{
  "id": "уникальный_id",
  "title": "Название раздела или страницы",
  "url": "/slug-страницы",
  "is_folder": true/false (true для разделов/категорий, false для конечных страниц),
  "cluster_id": "ID_кластера" или null,
  "page_type": "Категория" | "Услуга" | "Информационная" | "Карточка товара" | "Главная" | null,
  "children": [ ...вложенные узлы... ]
}

Правила:
1. Корневой элемент всегда 1: Главная страница ("title": "Главная", "url": "/", "is_folder": true, "page_type": "Главная").
2. Вложи все кластеры в логичную иерархию (Категории -> Подкатегории / Услуги -> Страницы).
3. Каждому кластеру должна соответствовать релевантная страница с указанием "cluster_id".
4. Если указан mode="incremental", СОХРАНИ существующую структуру и встрой новые нераспределённые кластеры в подходящие разделы.
"""

    user_prompt = f"САЙТ: {domain}\n"
    user_prompt += f"КЛАСТЕРЫ ДЛЯ РАЗМЕЩЕНИЯ:\n{json.dumps(clusters, ensure_ascii=False, indent=2)}\n"

    if req.mode == "incremental" and existing_structure:
        user_prompt += f"\nТЕКУЩАЯ СТРУКТУРА СУЩЕСТВУЕТ:\n{json.dumps(existing_structure, ensure_ascii=False, indent=2)}\nДобавь только недостающие кластеры в существующие разделы."
    else:
        user_prompt += "\nСформируй структуру с нуля."

    try:
        client = OpenAI(api_key=Config.OPENAI_API_KEY, base_url=Config.BASE_URL)
        response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )

        raw_content = response.choices[0].message.content or ""
        cleaned = raw_content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        data = json.loads(cleaned)
        struct_res = data.get("structure") or data.get("tree") or [data]
        if isinstance(struct_res, dict):
            struct_res = [struct_res]

        # Save generated structure
        json_str = json.dumps(struct_res, ensure_ascii=False)
        with get_db_cursor(commit=True) as (conn, cur):
            if Config.DB_TYPE == "postgresql":
                cur.execute(
                    """
                    INSERT INTO site_structure (user_id, site_url, structure_json)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, site_url) DO UPDATE SET structure_json = EXCLUDED.structure_json, updated_at = NOW()
                    """,
                    (current_user.user_id, domain, json_str)
                )
            else:
                cur.execute(
                    """
                    INSERT INTO site_structure (user_id, site_url, structure_json)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE structure_json = VALUES(structure_json)
                    """,
                    (current_user.user_id, domain, json_str)
                )

        return {"success": True, "structure": struct_res}

    except Exception as e:
        logger.error(f"Error generating structure: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации структуры через LLM: {str(e)}")


# --- Page Types Endpoints ---

DEFAULT_PAGE_TYPES = [
    {"name": "Главная", "icon": "fa-home", "color": "#10b981", "template_description": "Главная страница сайта"},
    {"name": "Категория", "icon": "fa-folder", "color": "#f59e0b", "template_description": "Раздел каталога или категорий услуг"},
    {"name": "Услуга", "icon": "fa-concierge-bell", "color": "#8b5cf6", "template_description": "Посадочная страница отдельной услуги"},
    {"name": "Информационная", "icon": "fa-newspaper", "color": "#3b82f6", "template_description": "Статья, новость или гайд"},
    {"name": "Карточка товара", "icon": "fa-box", "color": "#ec4899", "template_description": "Страница конкретного товара"}
]

@router.get("/api/page-types")
async def get_page_types(
    current_user: TokenData = Depends(get_current_user)
):
    with get_db_cursor(dictionary=True) as (conn, cur):
        cur.execute(
            "SELECT id, name, icon, color, template_description FROM page_types WHERE user_id = %s ORDER BY id ASC",
            (current_user.user_id,)
        )
        rows = cur.fetchall()
        
        # If user has no custom page types, return defaults
        if not rows:
            return {"types": DEFAULT_PAGE_TYPES}
            
        return {"types": rows}


@router.post("/api/page-types")
async def create_page_type(
    req: PageTypeCreateRequest,
    current_user: TokenData = Depends(get_current_user)
):
    with get_db_cursor(commit=True) as (conn, cur):
        cur.execute(
            """
            INSERT INTO page_types (user_id, name, icon, color, template_description)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (current_user.user_id, req.name, req.icon, req.color, req.template_description)
        )
    return {"success": True, "message": "Тип страницы успешно создан"}


@router.put("/api/page-types/{type_id}")
async def update_page_type(
    type_id: int,
    req: PageTypeUpdateRequest,
    current_user: TokenData = Depends(get_current_user)
):
    with get_db_cursor(commit=True) as (conn, cur):
        cur.execute(
            """
            UPDATE page_types SET name = %s, icon = %s, color = %s, template_description = %s
            WHERE id = %s AND user_id = %s
            """,
            (req.name, req.icon, req.color, req.template_description, type_id, current_user.user_id)
        )
    return {"success": True, "message": "Тип страницы обновлён"}


@router.delete("/api/page-types/{type_id}")
async def delete_page_type(
    type_id: int,
    current_user: TokenData = Depends(get_current_user)
):
    with get_db_cursor(commit=True) as (conn, cur):
        cur.execute(
            "DELETE FROM page_types WHERE id = %s AND user_id = %s",
            (type_id, current_user.user_id)
        )
    return {"success": True, "message": "Тип страницы удалён"}
