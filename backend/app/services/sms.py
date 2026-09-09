"""短信验证码服务:发送(频控+阿里云直调)/校验消费。

约定:
- 验证码明文绝不入库、绝不进日志,只存 sha256(code+phone+SECRET_KEY 盐);
- 未配置阿里云 4 项密钥时降级为 console 通道(仅日志),sms_debug=True 时
  响应附带 debug_code 供联调(生产必须关闭);
- 阿里云不可达/发送失败不抛 500:验证码已入库仍可校验,保证联调不中断。
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.http_client import get_http_client
from ..core.response import APIError
from ..models.sms_code import SmsCode

logger = logging.getLogger("app.sms")

PHONE_PATTERN = r"^1[3-9]\d{9}$"
# 同一手机号两条验证码的最小间隔(秒),响应中的 cooldown 同步使用该值
COOLDOWN_SEC = 60
_PURPOSES = ("login", "bind")


def _mask(phone: str) -> str:
    """日志脱敏:138****1234。"""
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else "***"


def _hash_code(code: str, phone: str) -> str:
    """验证码哈希:sha256(code + phone + SECRET_KEY 盐),定长 64 位十六进制。"""
    return hashlib.sha256(f"{code}{phone}{get_settings().secret_key}".encode("utf-8")).hexdigest()


def _pct(value: str) -> str:
    """阿里云 RPC 签名用的 popen 编码(保留字符集为空)。"""
    return quote(str(value), safe="")


async def _send_via_aliyun(phone: str, code: str) -> bool:
    """阿里云 Dysmsapi RPC 直调(不装 SDK):Code==OK 视为发送成功。"""
    settings = get_settings()
    params: dict[str, str] = {
        "Action": "SendSms",
        "Version": "2017-05-25",
        "Format": "JSON",
        "AccessKeyId": settings.aliyun_sms_access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "RegionId": "cn-hangzhou",
        "PhoneNumbers": phone,
        "SignName": settings.aliyun_sms_sign_name,
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": json.dumps({"code": code}, separators=(",", ":")),
    }
    # 1. 除 Signature 外按 key 排序 → popen 编码后拼 k=v& 串
    canonical = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items()))
    # 2. 待签串:GET&%2F&<popen(规范化串)>
    string_to_sign = f"GET&%2F&{_pct(canonical)}"
    key = (settings.aliyun_sms_access_key_secret + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode("utf-8")
    # 3. Signature 参数同样 popen 编码后追加(不再参与排序)
    url = f"https://{settings.aliyun_sms_endpoint}/?{canonical}&Signature={_pct(signature)}"

    client = get_http_client()
    resp = await client.get(url, timeout=10)
    data = resp.json()
    if str(data.get("Code", "")).upper() != "OK":
        logger.error(
            "阿里云短信发送失败 phone=%s Code=%s Message=%s",
            _mask(phone), data.get("Code"), data.get("Message"),
        )
        return False
    logger.info("阿里云短信发送成功 phone=%s", _mask(phone))
    return True


async def send_code(db: AsyncSession, phone: str, purpose: str, ip: str | None) -> dict:
    """发送验证码:格式校验 → 频控 → 生成入库 → 走阿里云或 console 通道。"""
    settings = get_settings()
    if not isinstance(phone, str) or not re.fullmatch(PHONE_PATTERN, phone):
        raise APIError(400, "手机号格式不正确")
    if purpose not in _PURPOSES:
        raise APIError(400, "短信用途不支持")

    # created_at 显式取本地时间,避免 SQLite(CURRENT_TIMESTAMP 为 UTC)与
    # MySQL(NOW() 为本地时间)默认值口径不一致导致频控窗口漂移
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    recent = await db.scalar(
        select(func.count()).select_from(SmsCode).where(
            SmsCode.phone == phone,
            SmsCode.created_at >= now - timedelta(seconds=COOLDOWN_SEC),
        )
    )
    if recent:
        raise APIError(429, "发送过于频繁,请稍后再试")

    phone_today = await db.scalar(
        select(func.count()).select_from(SmsCode).where(
            SmsCode.phone == phone, SmsCode.created_at >= day_start
        )
    )
    if phone_today >= settings.sms_send_per_day:
        raise APIError(429, "今日发送次数已达上限")

    if ip:
        ip_today = await db.scalar(
            select(func.count()).select_from(SmsCode).where(
                SmsCode.ip == ip, SmsCode.created_at >= day_start
            )
        )
        if ip_today >= settings.sms_ip_send_per_day:
            raise APIError(429, "当前 IP 今日发送次数已达上限")

    code = f"{secrets.randbelow(1000000):06d}"
    record = SmsCode(
        phone=phone,
        purpose=purpose,
        code_hash=_hash_code(code, phone),
        expires_at=now + timedelta(seconds=settings.sms_code_expire_sec),
        attempts=0,
        used_at=None,
        ip=ip or None,
        created_at=now,
    )
    db.add(record)
    await db.commit()  # 先入库再发送,即使发送失败验证码仍可校验(联调保障)

    result: dict = {"sent": False, "channel": "console", "cooldown": COOLDOWN_SEC}
    aliyun_ready = all([
        settings.aliyun_sms_access_key_id,
        settings.aliyun_sms_access_key_secret,
        settings.aliyun_sms_sign_name,
        settings.aliyun_sms_template_code,
    ])
    if aliyun_ready:
        try:
            sent = await _send_via_aliyun(phone, code)
            result["sent"] = sent
            result["channel"] = "aliyun" if sent else "console"
        except Exception:  # noqa: BLE001 发送失败不中断流程,验证码已入库可用
            logger.exception("阿里云短信发送异常 phone=%s", _mask(phone))
            result["sent"] = False
            result["channel"] = "console"
    else:
        logger.warning("SMS 未配置,验证码已生成 phone=%s", _mask(phone))
        if settings.sms_debug:
            result["debug_code"] = code
    return result


async def verify_code(db: AsyncSession, phone: str, purpose: str, code: str) -> None:
    """校验并消费验证码:取该 phone+purpose 最新一条未使用记录,失败直接抛 APIError。"""
    settings = get_settings()
    record = await db.scalar(
        select(SmsCode)
        .where(
            SmsCode.phone == phone,
            SmsCode.purpose == purpose,
            SmsCode.used_at.is_(None),
        )
        .order_by(SmsCode.id.desc())
        .limit(1)
    )
    if record is None:
        raise APIError(401, "验证码无效或已过期")
    if record.expires_at <= datetime.now():
        raise APIError(401, "验证码已过期,请重新获取")
    if record.attempts >= settings.sms_code_max_attempts:
        raise APIError(401, "验证码错误次数过多,已失效,请重新获取")
    if not hmac.compare_digest(record.code_hash, _hash_code(code or "", phone)):
        record.attempts = (record.attempts or 0) + 1
        await db.commit()
        raise APIError(401, "验证码错误")
    record.used_at = datetime.now()
    await db.commit()
