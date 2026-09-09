"""支付适配层:支付宝沙箱(真实网关)与内置模拟收银台双模式。

- 未配置支付宝密钥时 is_alipay_enabled() 为 False,下单走内置模拟收银台
  (前端 pay.html 模拟扫码→确认支付→mock-pay 入账),零配置可演示完整闭环;
- 配置 ALIPAY_APP_ID/PRIVATE_KEY/ALIPAY_PUBLIC_KEY 后走真实支付宝沙箱:
  下单返回 alipay.trade.page.pay 跳转 URL,异步 notify 验签入账;本地开发无公网
  时用 return_url 回跳后调 alipay.trade.query 同步查单闭环(见 routers/wallet.py);
- 签名 RSA2(SHA256withRSA):私钥签名 / 支付宝公钥验签;
- 私钥与支付宝公钥均支持「纯 base64 体」或「PEM 全文」两种配置格式。
"""
import base64
import json
import logging
from datetime import datetime
from urllib.parse import quote, urlencode

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

from ..core.config import get_settings
from ..core.http_client import get_http_client
from ..core.response import APIError

logger = logging.getLogger("app.payment")

# 参与签名的公共参数固定值
_SIGN_TYPE = "RSA2"
_CHARSET = "utf-8"
_VERSION = "1.0"
_FORMAT = "JSON"


def is_alipay_enabled() -> bool:
    """支付宝沙箱是否已配置齐备(app_id + 应用私钥 + 支付宝公钥)。"""
    s = get_settings()
    return bool(s.alipay_app_id and s.alipay_private_key and s.alipay_public_key)


# ---------- 密钥装载 ----------

def _wrap_pem(body: str, marker: str) -> bytes:
    """把纯 base64 密钥体包装成 PEM;已是 PEM 全文则原样使用。"""
    text = body.strip()
    if "-----BEGIN" in text:
        return text.encode()
    lines = "\n".join(text[i:i + 64] for i in range(0, len(text), 64))
    return f"-----BEGIN {marker}-----\n{lines}\n-----END {marker}-----".encode()


def _load_private_key():
    """加载应用私钥:先按 PKCS8,失败回退 PKCS1。"""
    raw = get_settings().alipay_private_key
    if not raw:
        raise APIError(500, "支付私钥未配置")
    pem = _wrap_pem(raw, "PRIVATE KEY")
    try:
        return serialization.load_pem_private_key(pem, password=None)
    except (ValueError, TypeError):
        pass
    pem1 = _wrap_pem(raw, "RSA PRIVATE KEY")
    try:
        return serialization.load_pem_private_key(pem1, password=None)
    except (ValueError, TypeError) as exc:
        raise APIError(500, "支付私钥配置无效,请检查 ALIPAY_PRIVATE_KEY") from exc


def _load_public_key():
    """加载支付宝公钥(用于验签;注意不是应用自己的公钥)。"""
    raw = get_settings().alipay_public_key
    if not raw:
        raise APIError(500, "支付宝公钥未配置")
    pem = _wrap_pem(raw, "PUBLIC KEY")
    try:
        return serialization.load_pem_public_key(pem)
    except (ValueError, TypeError) as exc:
        raise APIError(500, "支付宝公钥配置无效,请检查 ALIPAY_PUBLIC_KEY") from exc


# ---------- 签名/验签 ----------

def _payload_string(params: dict) -> str:
    """待签串:过滤空值与 sign/sign_type,按 key ASCII 升序拼 k=v&(值不做 URL 编码)。"""
    filtered = {
        k: v for k, v in params.items()
        if k not in ("sign", "sign_type") and v not in (None, "")
    }
    return "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))


def sign_params(params: dict) -> str:
    """RSA2 签名:SHA256withRSA,结果 base64 字符串。"""
    data = _payload_string(params).encode()
    return base64.b64encode(_load_private_key().sign(data, padding.PKCS1v15(), hashes.SHA256())).decode()


def verify_signature(params: dict) -> bool:
    """验签(notify/return 回执):用支付宝公钥校验 sign;异常一律 False。"""
    sign = params.get("sign")
    if not sign:
        return False
    try:
        data = _payload_string(params).encode()
        signature = base64.b64decode(sign)
        public_key = _load_public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            return False
        public_key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError, TypeError) as exc:
        logger.warning("支付宝验签失败: %s", exc)
        return False


# ---------- 下单/查单 ----------

def build_pay_url(order) -> str | None:
    """构造 alipay.trade.page.pay 页面支付跳转 URL;未启用支付宝返回 None。"""
    if not is_alipay_enabled():
        return None
    s = get_settings()
    params: dict = {
        "app_id": s.alipay_app_id,
        "method": "alipay.trade.page.pay",
        "format": _FORMAT,
        "charset": _CHARSET,
        "sign_type": _SIGN_TYPE,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": _VERSION,
        # 充值金额以「元」两位小数表达(口径:1 积分 = 1 元)
        "biz_content": json.dumps({
            "out_trade_no": order.order_no,
            "product_code": "FAST_INSTANT_TRADE_PAY",
            "total_amount": f"{order.amount:.2f}",
            "subject": f"积分充值-{order.points}积分",
        }, ensure_ascii=False),
    }
    if s.alipay_notify_url:
        params["notify_url"] = s.alipay_notify_url
    if s.alipay_return_url:
        params["return_url"] = s.alipay_return_url
    params["sign"] = sign_params(params)
    return f"{s.alipay_gateway}?{urlencode(params, quote_via=quote)}"


async def query_trade_status(order_no: str) -> str | None:
    """alipay.trade.query 同步查单:返回上游 trade_status(已支付为 TRADE_SUCCESS/
    TRADE_FINISHED);未启用支付宝或查询失败一律返回 None(不抛 500,由调用方兜底)。"""
    if not is_alipay_enabled():
        return None
    s = get_settings()
    params: dict = {
        "app_id": s.alipay_app_id,
        "method": "alipay.trade.query",
        "format": _FORMAT,
        "charset": _CHARSET,
        "sign_type": _SIGN_TYPE,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": _VERSION,
        "biz_content": json.dumps({"out_trade_no": order_no}, ensure_ascii=False),
    }
    params["sign"] = sign_params(params)
    try:
        client = get_http_client()
        resp = await client.post(
            s.alipay_gateway,
            data=params,
            timeout=15,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 查单失败不影响订单状态机
        logger.warning("支付宝查单失败(order_no=%s): %s", order_no, exc)
        return None
    status = (data.get("alipay_trade_query_response") or {}).get("trade_status")
    if status:
        return str(status)
    logger.warning("支付宝查单响应异常(order_no=%s): %s", order_no, str(data)[:300])
    return None
