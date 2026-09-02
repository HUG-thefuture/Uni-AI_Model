-- 成员2(WP04/06/07)配套的支撑表 MySQL 8.0 建表脚本
-- 本脚本只负责 chat_sessions / chat_messages / api_usage_logs 三张表。
-- 去重口径:consumption_records / operation_logs / api_keys / users /
-- user_profiles / wallets / invoices / recharge_orders 的权威 DDL 统一在
-- sql/003_member4_wallets_recharge_orders.sql,本脚本不再建这两类表,
-- 避免两版结构不一致导致“先执行者胜、后执行者被静默跳过”。
USE ai_portal;

CREATE TABLE IF NOT EXISTS chat_sessions (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  title       VARCHAR(100)    NOT NULL COMMENT '首条消息前 20 字',
  model_id    BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 models.id',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_session_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='对话会话表';

CREATE TABLE IF NOT EXISTS chat_messages (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id  BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 chat_sessions.id',
  role        VARCHAR(20)     NOT NULL COMMENT 'user / assistant',
  content     TEXT            NOT NULL,
  model_id    BIGINT UNSIGNED DEFAULT NULL,
  tokens_used INT             NOT NULL DEFAULT 0,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_msg_session_created (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='对话消息表';

-- CREATE TABLE IF NOT EXISTS api_keys (
--   id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
--   user_id     BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
--   name        VARCHAR(100)    NOT NULL COMMENT 'Key 名称',
--   key_prefix  VARCHAR(16)     NOT NULL COMMENT '明文前缀 sk-xxxxxx',
--   key_hash    VARCHAR(64)     NOT NULL COMMENT 'sha256(明文),不存明文',
--   status      VARCHAR(20)     NOT NULL DEFAULT 'enabled' COMMENT 'enabled / disabled',
--   use_count   BIGINT          NOT NULL DEFAULT 0,
--   expires_at  DATETIME        DEFAULT NULL,
--   created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (id),
--   UNIQUE KEY uk_key_hash (key_hash)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='开放平台 API Key';

CREATE TABLE IF NOT EXISTS api_usage_logs (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  key_id      BIGINT UNSIGNED DEFAULT NULL,
  user_id     BIGINT UNSIGNED DEFAULT NULL,
  path        VARCHAR(200)    NOT NULL,
  model_id    BIGINT UNSIGNED DEFAULT NULL,
  status_code INT             NOT NULL,
  latency_ms  BIGINT          NOT NULL DEFAULT 0,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_usage_key_created (key_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='开放平台调用统计';

