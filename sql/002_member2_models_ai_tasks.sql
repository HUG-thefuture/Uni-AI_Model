-- 成员2(WP01)负责的三张表 MySQL 8.0 建表脚本
-- 口径:与 docs/数据字典.md 一致(逻辑外键、utf8mb4、时间 DATETIME 默认当前时间)
-- 执行人:成员4(8/29 晚,与 users/user_profiles/wallets 一并执行;
-- users 三表权威 DDL 见 sql/003_member4_wallets_recharge_orders.sql)
USE ai_portal;

CREATE TABLE IF NOT EXISTS models (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name            VARCHAR(100)    NOT NULL COMMENT '展示名',
  model_code      VARCHAR(200)    NOT NULL COMMENT '厂商调用名,如 Qwen/Qwen2.5-7B-Instruct',
  provider_type   VARCHAR(20)     NOT NULL COMMENT 'online / local',
  model_type      VARCHAR(20)     NOT NULL COMMENT 'text / image / audio / video',
  vendor          VARCHAR(30)     NOT NULL COMMENT 'siliconflow / ollama / mock',
  endpoint        VARCHAR(255)    DEFAULT NULL COMMENT '自定义端点(本地模型用)',
  price_per_call  BIGINT          NOT NULL DEFAULT 0 COMMENT '积分点/次(整数)',
  max_duration_sec BIGINT         DEFAULT NULL COMMENT '音视频时长上限(秒)',
  status          VARCHAR(20)     NOT NULL DEFAULT 'enabled' COMMENT 'enabled / disabled',
  config_json     TEXT            COMMENT '非敏感参数 JSON(严禁存密钥)',
  description     VARCHAR(500)    DEFAULT NULL COMMENT '模型说明',
  capability_tags JSON            DEFAULT NULL COMMENT '能力标签数组',
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_model_code_provider (model_code, provider_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='模型元数据表';

CREATE TABLE IF NOT EXISTS ai_tasks (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id    VARCHAR(64)     NOT NULL COMMENT '链路 ID',
  user_id       BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  model_id      BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 models.id',
  task_type     VARCHAR(20)     NOT NULL COMMENT 'text / image / audio_clone / asr / video',
  prompt        TEXT            COMMENT '用户输入',
  params_json   TEXT            COMMENT '调用参数 JSON',
  status        VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/succeeded/failed',
  result_text   TEXT            COMMENT '文本结果',
  result_url    VARCHAR(500)    DEFAULT NULL COMMENT '文件结果地址',
  error_message VARCHAR(500)    DEFAULT NULL COMMENT '失败原因(中文)',
  cost          BIGINT          NOT NULL DEFAULT 0 COMMENT '消耗积分点(失败为 0)',
  cost_status   VARCHAR(20)     NOT NULL DEFAULT 'frozen' COMMENT 'frozen/settled/refunded',
  latency_ms    BIGINT          DEFAULT NULL COMMENT '总耗时(毫秒)',
  created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_user_created (user_id, created_at),
  KEY idx_status_created (status, created_at),
  KEY idx_task_type (task_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='AI 任务表(四类统一)';

CREATE TABLE IF NOT EXISTS ai_call_logs (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id  VARCHAR(64)     NOT NULL COMMENT '链路 ID',
  user_id     BIGINT UNSIGNED DEFAULT NULL COMMENT '逻辑外键 users.id',
  model_id    BIGINT UNSIGNED DEFAULT NULL COMMENT '逻辑外键 models.id',
  provider    VARCHAR(30)     NOT NULL COMMENT 'siliconflow / ollama / mock',
  latency_ms  BIGINT          NOT NULL DEFAULT 0 COMMENT '耗时(毫秒)',
  success     TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '是否成功',
  error_code  VARCHAR(50)     DEFAULT NULL COMMENT '错误码(成功为空)',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_request_id (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='模型调用日志表';
