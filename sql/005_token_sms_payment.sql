-- 005: 计费升级(按token) + 短信验证 + 支付闭环 增量脚本
-- 说明:与 backend/app/schema_sync.py 的 ORM 增量同步口径一致(只增不删不改)。
-- 本脚本是给 MySQL 运维手工执行用的;常规部署直接 python -m app.init_db 即可自动补齐。

-- ===== Phase 2:按实际 token 计费 =====
ALTER TABLE `models`
    ADD COLUMN `billing_mode` VARCHAR(20) NOT NULL DEFAULT 'per_call' COMMENT '计费方式: per_call(按次) / per_token(按实际token)' AFTER `price_per_call`,
    ADD COLUMN `token_input_price` BIGINT NOT NULL DEFAULT 0 COMMENT '输入token成本单价(0.0001积分/千token,整数)' AFTER `billing_mode`,
    ADD COLUMN `token_output_price` BIGINT NOT NULL DEFAULT 0 COMMENT '输出token成本单价(0.0001积分/千token,整数)' AFTER `token_input_price`,
    ADD COLUMN `token_markup_pct` INT NULL COMMENT 'token售价加价百分比(130=成本加价30%);NULL 时用全局 TOKEN_MARKUP_PCT' AFTER `token_output_price`;

ALTER TABLE `wallets`
    ADD COLUMN `credit_remainder` BIGINT NOT NULL DEFAULT 0 COMMENT 'token计费小额累积器(0.0001积分,满10000并入余额扣减)' AFTER `total_consumed`;

ALTER TABLE `ai_tasks`
    ADD COLUMN `frozen_cost` BIGINT NOT NULL DEFAULT 0 COMMENT '预冻结积分(按token计费时为预扣估算值)' AFTER `cost_status`,
    ADD COLUMN `prompt_tokens` BIGINT NULL COMMENT '输入 token 数(来自上游 usage)' AFTER `frozen_cost`,
    ADD COLUMN `completion_tokens` BIGINT NULL COMMENT '输出 token 数(来自上游 usage)' AFTER `prompt_tokens`;

ALTER TABLE `ai_call_logs`
    ADD COLUMN `prompt_tokens` BIGINT NULL COMMENT '输入 token 数' AFTER `error_code`,
    ADD COLUMN `completion_tokens` BIGINT NULL COMMENT '输出 token 数' AFTER `prompt_tokens`,
    ADD COLUMN `total_tokens` BIGINT NULL COMMENT '总 token 数' AFTER `completion_tokens`;

-- ===== Phase 3:短信验证 =====
ALTER TABLE `users`
    ADD COLUMN `phone` VARCHAR(20) NULL COMMENT '手机号(唯一,短信登录身份;未绑定为 NULL)' AFTER `username`,
    ADD UNIQUE KEY `uk_users_phone` (`phone`);

CREATE TABLE IF NOT EXISTS `sms_codes` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `phone` VARCHAR(20) NOT NULL COMMENT '手机号',
    `purpose` VARCHAR(20) NOT NULL COMMENT '用途: login / bind',
    `code_hash` VARCHAR(128) NOT NULL COMMENT '验证码哈希(sha256+盐)',
    `expires_at` DATETIME NOT NULL COMMENT '过期时间',
    `attempts` SMALLINT NOT NULL DEFAULT 0 COMMENT '校验失败次数',
    `used_at` DATETIME NULL COMMENT '使用时间(非空即已消费)',
    `ip` VARCHAR(64) NULL COMMENT '发送来源 IP',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    KEY `idx_sms_phone_created` (`phone`, `created_at`),
    KEY `idx_sms_ip_created` (`ip`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信验证码表';
