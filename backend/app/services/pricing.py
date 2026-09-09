"""计价服务:按次(per_call)/按实际 token(per_token)两种计费方式的费用计算。

金额口径(全平台统一,2026-09-07 起按「元」记账):
- 账本内部单位为「微元」:1 元 = MICRO(1_000_000) 微元,即最小精度 0.000001 元;
- token 单价存于 models.token_input_price / token_output_price,
  单位 0.0001 元/千token(整数,见 models/model.py 注释);
  该单价为「供应商成本价」,用户售价 = 成本 × 加价比例(markup_pct):
  模型行 token_markup_pct 优先,为空回退全局 TOKEN_MARKUP_PCT(默认 130 = 加价 30%);
- token 费用(微元)= tokens * 售价 / 10,整数除法向下取整
  (单次舍入误差 < 0.000009 元,可忽略,无需累积器);
- usage 缺失时按「中英混合约 2 字符 ≈ 1 token」估算(与全组口径一致);
- 预扣估算按售价冻结(微元),实际结算按真实 usage 计算,多退少不补。
"""
import json

from ..core.config import get_settings
from ..models.model import Model

MICRO = 1_000_000  # 1 元 = 1_000_000 微元(0.000001 元/微元,与 services/billing.py 一致)
CHARS_PER_TOKEN = 2  # 估算口径:2 字符 ≈ 1 token
DEFAULT_MAX_TOKENS_CAP = 2048  # 预扣估算的输出 token 封顶
DEFAULT_MARKUP_PCT = 130  # 加价兜底值(仅配置非法时使用)


def to_yuan(micro: int | None) -> float:
    """微元 → 元(浮点,6 位小数);仅供 API 序列化展示,运算请保持微元整数。"""
    return round((micro or 0) / MICRO, 6)


def to_micro(yuan: int | float) -> int:
    """元 → 微元(整数);充值/开票等以元计的入口换算用。"""
    return int(round(float(yuan) * MICRO))


def estimate_tokens(text: str) -> int:
    """无 usage 时按字符数粗略估算(中英混合约 2 字符/token)。"""
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def estimate_tokens_from_chars(chars: int) -> int:
    """按字符数估算 token(供已拼好的历史上下文使用,免重复拼接字符串)。"""
    return max(1, (chars or 0) // CHARS_PER_TOKEN)


def _model_int_param(model: Model, key: str, default: int) -> int:
    """从 models.config_json 读取整数参数(max_tokens 等),非法回退默认值。"""
    try:
        if getattr(model, "config_json", None):
            cfg = json.loads(model.config_json)
            if isinstance(cfg, dict):
                value = int(cfg.get(key))
                if value > 0:
                    return value
    except (ValueError, TypeError):
        pass
    return default


def is_per_token(model: Model) -> bool:
    """模型是否按实际 token 计费(仅文本模型适用;其余一律按次)。"""
    return getattr(model, "billing_mode", "per_call") == "per_token"


def markup_pct(model: Model) -> int:
    """该模型的售价加价百分比:模型行覆盖值 → 全局 TOKEN_MARKUP_PCT。"""
    value = getattr(model, "token_markup_pct", None)
    if value is not None and value >= 1:
        return int(value)
    settings_value = get_settings().token_markup_pct
    return settings_value if settings_value >= 1 else DEFAULT_MARKUP_PCT


def sell_prices(model: Model) -> tuple[int, int]:
    """用户售价(0.0001 元/千token):成本价 × 加价比例,整数。"""
    pct = markup_pct(model)
    sell_in = (model.token_input_price * pct + 50) // 100  # 四舍五入到整数
    sell_out = (model.token_output_price * pct + 50) // 100
    return max(0, sell_in), max(0, sell_out)


def cost_micro(model: Model, prompt_tokens: int, completion_tokens: int) -> int | None:
    """按 token 计费的用户费用(微元,按售价);per_call 模型返回 None。

    售价单位 0.0001 元/千token → 每 token 为 售价×10⁻⁷ 元 = 售价/10 微元。
    """
    if not is_per_token(model):
        return None
    sell_in, sell_out = sell_prices(model)
    micro = (max(0, prompt_tokens) * sell_in
             + max(0, completion_tokens) * sell_out) // 10
    return max(0, micro)


def provider_cost_micro(model: Model, prompt_tokens: int, completion_tokens: int) -> int | None:
    """供应商成本(微元,按成本价,不加价);用于毛利报表;per_call 返回 None。"""
    if not is_per_token(model):
        return None
    micro = (max(0, prompt_tokens) * model.token_input_price
             + max(0, completion_tokens) * model.token_output_price) // 10
    return max(0, micro)


def per_call_micro(model: Model, quantity: int = 1) -> int:
    """按次计费成本(微元):price_per_call 为供应商成本单价(元/张·条·次)。

    quantity 为本次任务的数量:图像=生成张数,视频=条数,音频/其他=1。
    """
    unit = int(round(float(model.price_per_call or 0) * MICRO))
    return max(0, unit) * max(1, int(quantity))


def per_call_sell_micro(model: Model, quantity: int = 1) -> int:
    """按次计费售价(微元):成本单价 × 加价比例 × 数量,与 token 计费同口径盈利。"""
    pct = markup_pct(model)
    unit = int(round(float(model.price_per_call or 0) * MICRO * pct / 100))
    return max(0, unit) * max(1, int(quantity))


def freeze_amount(model: Model, prompt_chars: int) -> int:
    """预扣冻结额(微元):per_call 取单价;per_token 按「输入估算 + 输出封顶」估算。

    prompt_chars 须含历史上下文字符(调用方拼接),输出按 config_json.max_tokens
    (缺省 2048)封顶;估算按售价,保守偏大,实际结算后差额退回。
    """
    if not is_per_token(model):
        return per_call_sell_micro(model)
    sell_in, sell_out = sell_prices(model)
    in_tokens = max(1, (prompt_chars or 0) // CHARS_PER_TOKEN)
    out_tokens = _model_int_param(model, "max_tokens", DEFAULT_MAX_TOKENS_CAP)
    micro = (in_tokens * sell_in + out_tokens * sell_out) // 10
    return max(0, micro)
