"""SQLAlchemy 模型包:显式注册全部模型到 Base.metadata。

任何 create_all 之前必须先 import 本包;新增表时在此同步登记,
否则自动建表会静默缺失(init_db 会按期望清单校验并报错)。
"""
from .ai_call_log import AiCallLog
from .ai_task import AiTask
from .api_key import ApiKey
from .consumption_record import ConsumptionRecord
from .invoice import Invoice
from .model import Model
from .operation_log import OperationLog
from .recharge_order import RechargeOrder
from .support import ApiUsageLog, ChatMessage, ChatSession
from .user import User, UserProfile, Wallet

__all__ = [
    "AiCallLog",
    "AiTask",
    "ApiKey",
    "ApiUsageLog",
    "ChatMessage",
    "ChatSession",
    "ConsumptionRecord",
    "Invoice",
    "Model",
    "OperationLog",
    "RechargeOrder",
    "User",
    "UserProfile",
    "Wallet",
]
