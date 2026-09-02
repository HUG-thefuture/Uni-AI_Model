"""建表入口:python -m app.init_db(在 backend/ 目录下执行)。

全量自动建表:users/user_profiles/wallets、models/ai_tasks/ai_call_logs、
chat_sessions/chat_messages/api_usage_logs、api_keys/consumption_records/
operation_logs/recharge_orders/invoices,共 14 张(与 sql/ 目录脚本同口径)。
只适用于空库/幂等补建;已存在表不会被 create_all 变更列结构。
"""
import sys

from .core.db import init_db


def main() -> int:
    try:
        tables = init_db()
    except Exception as exc:  # noqa: BLE001 给 CLI 用户明确中文错误
        print(f"建表失败: {exc}", file=sys.stderr)
        return 1
    print(f"建表完成,共 {len(tables)} 张表:")
    for name in tables:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
