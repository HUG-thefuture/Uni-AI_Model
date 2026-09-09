-- 006: 账本单位迁移 积分 → 微元(1 元 = 1_000_000 微元,精度 0.000001 元),2026-09-07
-- 注:分两步换算(×10000 再 ×100),与 backend/scripts/migrate_ledger_to_yuan.py 的两个步骤一致。
-- 说明:代码已按「元」记账(账本内部微元)。已有数据的环境需执行一次本脚本;
-- 全新环境(init_db 建表)无需执行。等价的自动化脚本见 backend/scripts/migrate_ledger_to_yuan.py(带幂等标记表)。

UPDATE wallets SET
  balance = balance * 10000 + credit_remainder,
  credit_remainder = 0,
  total_recharged = total_recharged * 10000,
  total_consumed = total_consumed * 10000;

UPDATE consumption_records SET
  amount = amount * 10000,
  balance_before = balance_before * 10000,
  balance_after = balance_after * 10000;

UPDATE ai_tasks SET
  cost = cost * 10000,
  frozen_cost = frozen_cost * 10000;

-- recharge_orders.amount 本就是「元」,无需换算;points 列已弃用。
