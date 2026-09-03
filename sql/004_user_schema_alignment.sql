-- 用户 ORM 与既有 MySQL 表结构对齐（兼容 MySQL 5.7/8.0）
-- 执行前请先备份 ai_portal；脚本可重复执行。
USE ai_portal;

CREATE TABLE IF NOT EXISTS user_profiles (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL,
  nickname    VARCHAR(50)     DEFAULT NULL,
  avatar_url  VARCHAR(255)    DEFAULT NULL,
  phone       VARCHAR(20)     DEFAULT NULL,
  email       VARCHAR(100)    DEFAULT NULL,
  major       VARCHAR(100)    DEFAULT NULL,
  bio         VARCHAR(500)    DEFAULT NULL,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户资料表';

SET @users_updated_at_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND COLUMN_NAME = 'updated_at'
);
SET @users_updated_at_sql = IF(
  @users_updated_at_exists = 0,
  'ALTER TABLE users ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT ''更新时间''',
  'SELECT ''users.updated_at already exists'''
);
PREPARE users_updated_at_stmt FROM @users_updated_at_sql;
EXECUTE users_updated_at_stmt;
DEALLOCATE PREPARE users_updated_at_stmt;
