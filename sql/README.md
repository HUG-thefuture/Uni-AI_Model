# sql：数据库脚本

## 推荐入口

- 全新 MySQL 库：执行 `001_canonical_schema.sql`。
- 已有库或不确定由哪份旧脚本创建：在 `backend/` 执行
  `python -m app.schema_sync --apply`；该命令以 ORM 为准补齐缺表、缺列和缺索引，
  不删除字段或数据。
- 检查但不修改：`python -m app.schema_sync --check`。返回码为 1 表示仍有缺失结构。
- 一步完成结构对齐并写入模型种子：`python -m app.init_db`。

`002_member2_*.sql`、`003_member*.sql`、`004_user_schema_alignment.sql` 是历史拆分脚本，
保留用于追溯，不应再单独或按顺序执行。新库请使用 `001_canonical_schema.sql`；旧库请使用
程序同步入口，避免 `CREATE TABLE IF NOT EXISTS` 掩盖字段漂移。
