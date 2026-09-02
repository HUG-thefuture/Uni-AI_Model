# sql：数据库脚本（MySQL 8.0）

## 文件与执行顺序

按以下顺序执行一次即可（每张表在仓库内只定义一次，重复执行不会互相覆盖）：

1. `000_bootstrap.sql`：创建 `ai_portal` 库（utf8mb4）。
2. `002_member2_models_ai_tasks.sql`：models / ai_tasks / ai_call_logs。
3. `003_member2_support_tables.sql`：chat_sessions / chat_messages / api_usage_logs。
4. `003_member4_wallets_recharge_orders.sql`：users / user_profiles / wallets /
   recharge_orders / invoices / consumption_records / api_keys / operation_logs。

合计 14 张表，与 `backend/app/models/` 的 ORM 一一对应。

## 与 `python -m app.init_db` 的关系

- `python -m app.init_db`（在 backend/ 目录执行）会按 ORM 自动建同样的 14 张表，
  并在注册不全时直接报错，避免静默缺表。
- 两条路径二选一，不要在生产库混跑；`create_all` 只补建缺失表，
  不会给已存在的表补列或改结构，结构变更需要单独写迁移 SQL。

## 示例数据

演示账号/任务数据见 `backend/scripts/seed_demo.py`；
模型种子数据见 `backend/scripts/seed_models.py`（模板 `docs/model-config-template.json`）。
