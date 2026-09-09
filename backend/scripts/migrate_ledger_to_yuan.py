"""账本单位迁移:积分 → 元(微元记账,1 元 = 10_000 微元)。

2026-09-07 起平台按「元」计费:钱包余额/流水/任务费用全部改存微元
(0.0001 元),token 单价 0.0001 元/千token 口径不变,每次调用按真实
用量精确扣减(原 1 积分尾差累积器 wallets.credit_remainder 废弃,
迁移时并入余额)。

本脚本把存量数据一次性换算(×10_000),并写入标记表防止重复执行:
  - wallets.balance / total_recharged / total_consumed
  - wallets.credit_remainder(并入 balance 后清零)
  - consumption_records.amount / balance_before / balance_after
  - ai_tasks.cost / frozen_cost
  - recharge_orders.amount 本就是「元」,不换算;points 列已弃用,不迁移

用法(backend 目录、venv 下执行):
  python scripts/migrate_ledger_to_yuan.py            # 预览受影响行数
  python scripts/migrate_ledger_to_yuan.py --apply    # 执行迁移(仅可运行一次)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.db import engine  # noqa: E402

MARKER_TABLE = "schema_migrations"
MARKER_KEY = "20260907_ledger_unit_yuan"
MARKER_KEY_2 = "20260907_ledger_precision_1e6"

# (表, 参与换算的列;credit_remainder 特殊处理)
TARGETS = [
    ("wallets", ["balance", "total_recharged", "total_consumed"]),
    ("consumption_records", ["amount", "balance_before", "balance_after"]),
    ("ai_tasks", ["cost", "frozen_cost"]),
]


def _marker_ready(insp, marker_key: str) -> bool:
    if MARKER_TABLE not in insp.get_table_names():
        return False
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT 1 FROM {MARKER_TABLE} WHERE step = :k"), {"k": marker_key}
        ).first()
    return row is not None


def _run_step(insp, marker_key: str, factor: int, fold_remainder: bool, apply: bool) -> bool:
    """执行一步换算(×factor);标记已存在则跳过。返回是否实际执行。"""
    if _marker_ready(insp, marker_key):
        print(f"步骤 {marker_key} 已执行过,跳过")
        return False
    with engine.begin() as conn:
        for table, cols in TARGETS:
            sets = ", ".join(f"`{c}` = `{c}` * {factor}" for c in cols)
            conn.execute(text(f"UPDATE `{table}` SET {sets}"))
        if fold_remainder:
            conn.execute(text("UPDATE `wallets` SET `balance` = `balance` + `credit_remainder` * 100, `credit_remainder` = 0"))
        if MARKER_TABLE not in insp.get_table_names():
            conn.execute(text(
                f"CREATE TABLE {MARKER_TABLE} (step VARCHAR(64) PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
        conn.execute(text(f"INSERT INTO {MARKER_TABLE} (step) VALUES (:k)"), {"k": marker_key})
    print(f"步骤 {marker_key} 完成(×{factor})")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="账本单位迁移:积分 → 微元(元)")
    parser.add_argument("--apply", action="store_true", help="实际执行(默认仅预览)")
    args = parser.parse_args()

    insp = inspect(engine)
    if not args.apply:
        for table, cols in TARGETS:
            cols_sql = ", ".join(f"`{c}`" for c in cols)
            with engine.begin() as conn:
                count = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
                sample = conn.execute(text(f"SELECT {cols_sql} FROM `{table}` LIMIT 3")).all()
            print(f"  {table}: {count} 行,列 {cols} (样例 {sample})")
        print("预览完成(未写入)。确认后加 --apply 执行。")
        return
    _run_step(insp, MARKER_KEY, 10_000, fold_remainder=True, apply=True)
    _run_step(insp, MARKER_KEY_2, 100, fold_remainder=False, apply=True)
    print("迁移完成:账本单位为微元(1 元 = 1_000_000,精度 0.000001 元)。")

    with engine.begin() as conn:
        print("受影响行数预览:")
        for table, cols in TARGETS:
            cols_sql = ", ".join(f"`{c}`" for c in cols)
            count = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
            sample = conn.execute(text(f"SELECT {cols_sql} FROM `{table}` LIMIT 3")).all()
            print(f"  {table}: {count} 行,列 {cols} (样例 {sample})")

        if not args.apply:
            print("预览完成(未写入)。确认后加 --apply 执行。")
            return

        try:
            for table, cols in TARGETS:
                sets = ", ".join(f"`{c}` = `{c}` * 10000" for c in cols)
                conn.execute(text(f"UPDATE `{table}` SET {sets}"))
            # 尾差累积器并入余额后清零
            conn.execute(text("UPDATE `wallets` SET `balance` = `balance` + `credit_remainder`, `credit_remainder` = 0"))
            if MARKER_TABLE not in insp.get_table_names():
                conn.execute(text(
                    f"CREATE TABLE {MARKER_TABLE} (step VARCHAR(64) PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
                ))
            conn.execute(text(f"INSERT INTO {MARKER_TABLE} (step) VALUES (:k)"), {"k": MARKER_KEY})
            print("迁移完成:账本单位已换算为微元(1 元 = 10000)。")
        except Exception:
            raise


if __name__ == "__main__":
    main()
