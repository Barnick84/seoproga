import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user
from utils.db import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Wordstat"])


class WordstatSettingRequest(BaseModel):
    name: str
    device: str = "desktop"
    region: str = "213"
    region_name: str = "Москва"
    is_default: bool = False


class WordstatSettingDeleteRequest(BaseModel):
    id: int


@router.get("/api/wordstat-settings")
async def get_wordstat_settings(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT * FROM wordstat_settings WHERE user_id = %s ORDER BY is_default DESC, id ASC",
                (current_user.user_id,),
            )
            rows = cur.fetchall()
            for r in rows:
                r["is_default"] = bool(r["is_default"])
            return {"success": True, "settings": rows}
    except Exception as e:
        logger.error("Failed to fetch wordstat settings: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/wordstat-settings")
async def create_wordstat_setting(
    req: WordstatSettingRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            if req.is_default:
                cur.execute(
                    "UPDATE wordstat_settings SET is_default = 0 WHERE user_id = %s",
                    (current_user.user_id,),
                )
            cur.execute(
                """INSERT INTO wordstat_settings (user_id, name, device, region, region_name, is_default)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    current_user.user_id,
                    req.name,
                    req.device,
                    req.region,
                    req.region_name,
                    int(req.is_default),
                ),
            )
            return {"success": True, "id": cur.lastrowid}
    except Exception as e:
        logger.error("Failed to create wordstat setting: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/api/wordstat-settings/{setting_id}")
async def delete_wordstat_setting(
    setting_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        with get_db_cursor(commit=True) as (conn, cur):
            cur.execute(
                "DELETE FROM wordstat_settings WHERE id = %s AND user_id = %s",
                (setting_id, current_user.user_id),
            )
            return {"success": True}
    except Exception as e:
        logger.error("Failed to delete wordstat setting: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


YANDEX_GEO = [
    {"id": "225", "name": "Россия"},
    {"id": "213", "name": "Москва"},
    {"id": "1", "name": "Москва и область"},
    {"id": "2", "name": "Санкт-Петербург"},
    {"id": "3", "name": "Краснодарский край"},
    {"id": "4", "name": "Новосибирская область"},
    {"id": "5", "name": "Свердловская область"},
    {"id": "6", "name": "Республика Татарстан"},
    {"id": "7", "name": "Ростовская область"},
    {"id": "8", "name": "Республика Башкортостан"},
    {"id": "9", "name": "Самарская область"},
    {"id": "10", "name": "Челябинская область"},
    {"id": "11", "name": "Нижегородская область"},
    {"id": "12", "name": "Красноярский край"},
    {"id": "13", "name": "Пермский край"},
    {"id": "14", "name": "Воронежская область"},
    {"id": "15", "name": "Волгоградская область"},
    {"id": "16", "name": "Саратовская область"},
    {"id": "17", "name": "Оренбургская область"},
    {"id": "18", "name": "Кемеровская область"},
    {"id": "19", "name": "Алтайский край"},
    {"id": "20", "name": "Тюменская область"},
    {"id": "21", "name": "Удмуртская Республика"},
    {"id": "22", "name": "Иркутская область"},
    {"id": "23", "name": "Приморский край"},
    {"id": "24", "name": "Хабаровский край"},
    {"id": "25", "name": "Ярославская область"},
    {"id": "26", "name": "Ставропольский край"},
    {"id": "27", "name": "Тверская область"},
    {"id": "28", "name": "Омская область"},
    {"id": "29", "name": "Мурманская область"},
    {"id": "30", "name": "Ленинградская область"},
    {"id": "31", "name": "Ульяновская область"},
    {"id": "32", "name": "Тульская область"},
    {"id": "33", "name": "Владимирская область"},
    {"id": "34", "name": "Кировская область"},
    {"id": "35", "name": "Белгородская область"},
    {"id": "36", "name": "Калининградская область"},
    {"id": "37", "name": "Калужская область"},
    {"id": "38", "name": "Курская область"},
    {"id": "39", "name": "Липецкая область"},
    {"id": "40", "name": "Пензенская область"},
    {"id": "41", "name": "Рязанская область"},
    {"id": "42", "name": "Смоленская область"},
    {"id": "43", "name": "Тамбовская область"},
    {"id": "44", "name": "Астраханская область"},
    {"id": "45", "name": "Республика Карелия"},
    {"id": "46", "name": "Республика Крым"},
    {"id": "47", "name": "Чувашская Республика"},
    {"id": "48", "name": "Архангельская область"},
    {"id": "49", "name": "Вологодская область"},
    {"id": "50", "name": "Забайкальский край"},
    {"id": "51", "name": "Ивановская область"},
    {"id": "52", "name": "Костромская область"},
    {"id": "53", "name": "Курганская область"},
    {"id": "54", "name": "Магаданская область"},
    {"id": "55", "name": "Новгородская область"},
    {"id": "56", "name": "Псковская область"},
    {"id": "57", "name": "Республика Бурятия"},
    {"id": "58", "name": "Республика Дагестан"},
    {"id": "59", "name": "Республика Коми"},
    {"id": "60", "name": "Республика Марий Эл"},
    {"id": "61", "name": "Республика Мордовия"},
    {"id": "62", "name": "Республика Саха (Якутия)"},
    {"id": "63", "name": "Республика Северная Осетия — Алания"},
    {"id": "64", "name": "Республика Хакасия"},
    {"id": "65", "name": "Сахалинская область"},
    {"id": "66", "name": "Томская область"},
    {"id": "67", "name": "Ханты-Мансийский АО"},
    {"id": "68", "name": "Чукотский АО"},
    {"id": "69", "name": "Ямало-Ненецкий АО"},
    {"id": "70", "name": "Республика Адыгея"},
    {"id": "71", "name": "Республика Алтай"},
    {"id": "72", "name": "Республика Ингушетия"},
    {"id": "73", "name": "Республика Калмыкия"},
    {"id": "74", "name": "Республика Кабардино-Балкарская"},
    {"id": "75", "name": "Республика Карачаево-Черкесская"},
    {"id": "76", "name": "Республика Тыва"},
    {"id": "77", "name": "Чеченская Республика"},
    {"id": "78", "name": "Амурская область"},
    {"id": "79", "name": "Брянская область"},
    {"id": "80", "name": "Еврейская АО"},
    {"id": "81", "name": "Камчатский край"},
]


@router.get("/api/geo-regions")
async def get_geo_regions(current_user: TokenData = Depends(get_current_user)):
    return {"success": True, "regions": YANDEX_GEO}
