"""钱包与充值支付路由。

- 路径不含 /api 前缀,main.py 统一挂 settings.api_prefix;
- 充值为真实订单状态机:POST /recharge 建 pending 订单 → 收银台支付
  (支付宝沙箱跳转 / 内置模拟收银台) → 幂等入账;
- /notify/alipay 是支付宝异步通知(公开路由,明文 success/fail 响应,不走统一响应壳);
- /orders/{no}/sync 供本地开发(无公网 notify)在浏览器回跳后同步查单闭环。
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession


from ..core.response import APIError, ok
from ..core.deps import get_current_user
from ..schemas.admin_wallet import InvoiceCreate, InvoiceResponse
from ..schemas.payment import RechargeRequest
from ..schemas.wallet import RechargeResponse
from ..services import admin_wallet, payment, wallet
from ..services.pricing import to_micro, to_yuan
from ..core.db import get_async_db

logger = logging.getLogger("app.wallet")

router = APIRouter(
    prefix="/wallet",
    tags=["钱包"],
)

@router.get("/me")
async def my_wallet(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    w = await wallet.get_wallet(current_user.id, db)
    # 账本为微元(1 元 = 10_000 微元),对外统一输出「元」
    return ok({
        "balance": to_yuan(w.balance),
        "total_recharged": to_yuan(w.total_recharged),
        "total_consumed": to_yuan(w.total_consumed),
    })


@router.post("/recharge")
async def recharge(recharge_data: RechargeRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """充值下单:创建 pending 订单并返回收银台信息(此时未入账)。"""
    try:
        order, pay_info = await wallet.create_pending_order(
            db, current_user.id, recharge_data.amount, recharge_data.payment_method
        )
        data = RechargeResponse(
            order_no=order.order_no,
            amount=order.amount,
            payment_method=order.payment_method,
            status=order.status,
            created_at=order.created_at,
        ).model_dump(mode="json")
        data.update(pay_info)
        return ok(data)
    except APIError:
        raise
    except Exception:
        raise APIError(500, "充值失败，请稍后重试") from None


@router.get("/orders/{order_no}")
async def get_order(order_no: str, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """订单状态查询(前端轮询用);他人订单一律 404。待支付订单附收银台跳转地址。"""
    order = await wallet.get_order(db, current_user.id, order_no)
    pay_url = None
    if order.status == "pending" and order.payment_method == "alipay":
        pay_url = payment.build_pay_url(order)
    return ok({
        "order_no": order.order_no,
        "amount": order.amount,
        "payment_method": order.payment_method,
        "pay_mode": "alipay" if order.payment_method == "alipay" else "sandbox",
        "pay_url": pay_url,
        "status": order.status,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    })


@router.post("/orders/{order_no}/mock-pay")
async def mock_pay(order_no: str, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """内置模拟收银台「确认支付」:仅未配置支付宝时开放;幂等。"""
    if payment.is_alipay_enabled():
        raise APIError(403, "模拟支付已停用,请使用支付宝收银台完成支付")
    order = await wallet.get_order(db, current_user.id, order_no)
    order = await wallet.settle_order_payment(
        db, order.order_no, external_trade_no=f"MOCK-{order.order_no}", payment_method="mock"
    )
    return ok({"order_no": order.order_no, "status": order.status, "amount": order.amount})


@router.post("/orders/{order_no}/sync")
async def sync_order(order_no: str, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """同步查单闭环:本地开发无公网 notify 时,浏览器回跳后调 alipay.trade.query 确认。"""
    order = await wallet.get_order(db, current_user.id, order_no)
    if order.status != "paid":
        status = await payment.query_trade_status(order.order_no)
        if status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            order = await wallet.settle_order_payment(
                db, order.order_no,
                external_trade_no=f"ALIPAY-{order.order_no}", payment_method="alipay",
            )
    return ok({"order_no": order.order_no, "status": order.status, "amount": order.amount})


@router.post("/notify/alipay", include_in_schema=True)
async def alipay_notify(request: Request, db: AsyncSession = Depends(get_async_db)):
    """支付宝异步通知(公开路由):验签 → 幂等入账;必须明文返回 success/fail。"""
    try:
        form = await request.form()
        params = {k: v for k, v in form.items()}
    except Exception:  # noqa: BLE001
        return PlainTextResponse("fail")
    if not payment.verify_signature(params):
        return PlainTextResponse("fail")
    trade_status = str(params.get("trade_status") or "")
    order_no = str(params.get("out_trade_no") or "")
    trade_no = str(params.get("trade_no") or "")
    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED") and order_no:
        # 回执加固:核对 app_id 与订单金额一致后才入账,防止网关配置错乱/串单
        from ..core.config import get_settings
        if str(params.get("app_id") or "") != get_settings().alipay_app_id:
            return PlainTextResponse("fail")
        try:
            notified_amount = float(params.get("total_amount") or -1)
        except (TypeError, ValueError):
            return PlainTextResponse("fail")
        order = await wallet.find_order(db, order_no)
        if order is None:
            return PlainTextResponse("fail")
        if f"{notified_amount:.2f}" != f"{float(order.amount):.2f}":
            logger.warning("支付宝回执金额与订单不一致 order_no=%s notify=%s order=%s",
                           order_no, notified_amount, order.amount)
            return PlainTextResponse("fail")
        try:
            # 通知可能先于本地订单可见(主从延迟),异常时回 fail 让支付宝重试
            await wallet.settle_order_payment(db, order_no, external_trade_no=trade_no or f"ALIPAY-{order_no}",
                                              payment_method="alipay")
        except APIError as exc:
            if exc.status_code == 404:
                return PlainTextResponse("fail")
            return PlainTextResponse("success")  # 状态冲突等幂等场景
        except Exception:  # noqa: BLE001
            return PlainTextResponse("fail")
    return PlainTextResponse("success")


@router.get("/records")
async def get_records(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user), page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数")):
    stmt=await wallet.get_user_records(db,current_user.id,page,page_size)
    return ok(jsonable_encoder(stmt))


@router.get("/records/export")
async def export_records(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """账单流水 CSV 导出(UTF-8 BOM,Excel 可直接打开)。"""
    from fastapi.responses import Response
    csv_text = await wallet.export_records_csv(db, current_user.id)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=billing-records.csv"},
    )


@router.get("/invoices")
async def get_invoices(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
):
    return ok(jsonable_encoder(await wallet.get_user_invoices(db, current_user.id, page, page_size)))


@router.post("/invoices")
async def create_invoice(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    # 校验用户是否有足够的可开票金额
    w = await wallet.get_wallet(current_user.id, db)
    if w.total_recharged - w.total_consumed < to_micro(data.amount):
        raise APIError(400, "可开票余额不足")
    invoice = await admin_wallet.create_invoice(db, current_user.id, data)
    return ok(InvoiceResponse.model_validate(invoice).model_dump(mode="json"))
