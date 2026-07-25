import hashlib
import logging
import os

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from api.dependencies import TokenData, get_current_user
from utils.db import get_db_cursor

router = APIRouter(tags=["Billing"])
logger = logging.getLogger(__name__)


class CreatePaymentRequest(BaseModel):
    amount: float


class BillingHistoryResponse(BaseModel):
    success: bool
    billing: list
    payments: list


@router.get("/api/billing-history", response_model=BillingHistoryResponse)
async def get_billing_history(current_user: TokenData = Depends(get_current_user)):
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute(
                "SELECT id, user_id, amount, description, type, created_at FROM billing_history WHERE user_id = %s ORDER BY created_at DESC",
                (current_user.user_id,),
            )
            billing = cur.fetchall()

            cur.execute(
                "SELECT id, user_id, amount, currency, order_id, status, created_at FROM payment_history WHERE user_id = %s ORDER BY created_at DESC",
                (current_user.user_id,),
            )
            payments = cur.fetchall()

        return {"success": True, "billing": billing, "payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/create-payment")
async def create_payment(
    req: CreatePaymentRequest, current_user: TokenData = Depends(get_current_user)
):
    min_amount = 500
    if req.amount < min_amount:
        raise HTTPException(
            status_code=400, detail=f"Минимальная сумма пополнения {min_amount} руб."
        )

    shop_id = os.getenv("CARDLINK_SHOP_ID")
    token = os.getenv("CARDLINK_TOKEN")

    if not shop_id or not token:
        raise HTTPException(
            status_code=500, detail="Платёжный шлюз не настроен (CARDLINK_SHOP_ID, CARDLINK_TOKEN)"
        )

    import time

    order_id = f"ORDER_{int(time.time() * 1000)}_{current_user.user_id}"
    currency = "RUB"

    try:
        with get_db_cursor(commit=True, dictionary=False) as (conn, cur):
            cur.execute(
                "INSERT INTO payment_history (user_id, amount, currency, order_id, status) VALUES (%s, %s, %s, %s, %s)",
                (current_user.user_id, req.amount, currency, order_id, "pending"),
            )

        data = {
            "amount": str(req.amount),
            "order_id": order_id,
            "description": "Пополнение баланса в сервисе",
            "type": "normal",
            "shop_id": shop_id,
            "currency_in": currency,
            "payer_pays_commission": "1",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://cardlink.link/api/v1/bill/create",
                data=data,
                headers={"Authorization": f"Bearer {token}"},
            )

        res_data = response.json()
        if res_data.get("success") == True or res_data.get("success") == "true":
            payment_url = res_data.get("link_page_url") or res_data.get("link_url")
            return {"success": True, "payment_url": payment_url}
        else:
            logger.error(f"Cardlink API Error: {res_data}")
            raise HTTPException(status_code=500, detail="Ошибка создания платежа в Cardlink")

    except Exception as e:
        logger.error(f"Payment creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment-suceful")
@router.post("/payment-suceful/")
async def payment_successful(
    request: Request,
    InvId: str = Form(None),
    OutSum: str = Form(None),
    Status: str = Form(None),
    SignatureValue: str = Form(None),
):
    try:
        # Some payment gateways send JSON, others form data. Let's handle both.
        if request.headers.get("content-type") == "application/json":
            body = await request.json()
            logger.info(f"Cardlink JSON webhook payload: {body}")
            InvId = body.get("InvId", InvId)
            OutSum = body.get("OutSum", OutSum)
            Status = body.get("Status", Status)
            SignatureValue = body.get("SignatureValue", SignatureValue)
        else:
            form_data = await request.form()
            logger.info(f"Cardlink FORM webhook payload: {form_data}")

        logger.info(
            f"Cardlink webhook processed params: InvId={InvId}, OutSum={OutSum}, Status={Status}"
        )

        token = os.getenv("CARDLINK_TOKEN", "")

        if not InvId or not OutSum or not SignatureValue:
            return HTMLResponse(content="Missing params", status_code=400)

        # Cardlink sign: strtoupper(md5($OutSum . ":" . $InvId . ":" . $apiToken))
        sign_str = f"{OutSum}:{InvId}:{token}"
        expected_sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

        if SignatureValue.upper() != expected_sign:
            logger.error(f"Invalid Cardlink sign. Expected: {expected_sign}, Got: {SignatureValue}")
            return HTMLResponse(content="Invalid sign", status_code=400)

        if Status and Status.upper() != "SUCCESS":
            return HTMLResponse(content="Ignored non-success status", status_code=200)

        order_id = InvId
        amount = float(OutSum)

        try:
            with get_db_cursor(commit=False, dictionary=True) as (conn, cur):
                cur.execute(
                    "SELECT id, user_id, amount, currency, order_id, status, created_at FROM payment_history WHERE order_id = %s AND status = %s FOR UPDATE",
                    (order_id, "pending"),
                )
                payments = cur.fetchall()

                if not payments:
                    return HTMLResponse(content="Already processed or not found", status_code=200)

                payment = payments[0]

                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE id = %s",
                    (amount, payment["user_id"]),
                )
                cur.execute(
                    "UPDATE payment_history SET status = %s WHERE id = %s",
                    ("success", payment["id"]),
                )
                cur.execute(
                    "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                    (
                        payment["user_id"],
                        amount,
                        f"Пополнение баланса (Заказ {order_id})",
                        "deposit",
                    ),
                )
                conn.commit()
                return HTMLResponse(content="OK", status_code=200)
        except Exception as err:
            raise err

    except Exception as e:
        logger.error(f"Cardlink Callback error: {str(e)}")
        return HTMLResponse(content="Internal Server Error", status_code=500)


@router.get("/suceful")
@router.get("/suceful/")
async def suceful_page():
    return RedirectResponse(url="/public/suceful.html")


@router.get("/errore")
@router.get("/errore/")
async def errore_page():
    return RedirectResponse(url="/public/errore.html")
