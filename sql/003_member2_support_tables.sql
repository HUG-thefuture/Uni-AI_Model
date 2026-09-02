-- 成员2(WP04/06/07)配套的支撑表 MySQL 8.0 建表脚本
-- 说明:users/user_profiles/wallets 由成员1 的 001 脚本负责,此处不重复;
--       consumption_records / operation_logs / api_keys / api_usage_logs 归属成员4,
--       本脚本按 wp04/06 提示词口径先行落地,字段若与成员4 终版冲突,以成员4 DDL 为准。
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

CREATE TABLE IF NOT EXISTS consumption_records (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL,
  task_id     BIGINT UNSIGNED DEFAULT NULL,
  model_id    BIGINT UNSIGNED DEFAULT NULL,
  amount      BIGINT          NOT NULL COMMENT '消耗积分点(整数)',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_consume_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='消费流水(成员4 最小桩,TODO 字段对齐)';

CREATE TABLE IF NOT EXISTS operation_logs (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       BIGINT UNSIGNED DEFAULT NULL,
  action        VARCHAR(50)     NOT NULL,
  resource_type VARCHAR(50)     NOT NULL,
  resource_id   BIGINT UNSIGNED DEFAULT NULL,
  detail_json   TEXT            COMMENT '操作详情 JSON',
  created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_op_resource (resource_type, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='管理操作日志(成员4 最小桩)';
