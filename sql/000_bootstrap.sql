-- 建库引导脚本(原 README 中缺失的 init.sql 落点)
-- 用法:MySQL 中先执行本文件创建 ai_portal 库,
-- 再按 sql/README.md 顺序执行 002 / 003_member2 / 003_member4。
CREATE DATABASE IF NOT EXISTS ai_portal
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;
