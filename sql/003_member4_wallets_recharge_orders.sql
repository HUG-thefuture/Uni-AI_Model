-- 成员4(WP01)第一天 MySQL 脚本
-- 口径：与 docs/数据字典.md 与 docs/项目框架与任务分工.md 一致
-- 目的：完成钱包、充值与财务类基础表的建表，满足 8/29 接口前置需求
-- 执行方式：在 ai_portal 库中执行本脚本

USE ai_portal;

CREATE TABLE IF NOT EXISTS users (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户主键',
  username         VARCHAR(50)     NOT NULL COMMENT '用户名',
  password_hash    VARCHAR(255)    NOT NULL COMMENT '密码哈希',
  role             VARCHAR(20)     NOT NULL DEFAULT 'user' COMMENT 'user / admin',
  status           TINYINT         NOT NULL DEFAULT 1 COMMENT '1 启用 0 禁用',
  real_auth_status TINYINT         NOT NULL DEFAULT 0 COMMENT '0 未认证 1 已认证 2 审核中',
  school           VARCHAR(100)    DEFAULT NULL COMMENT '学校',
  created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username),
  KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户主表';

CREATE TABLE IF NOT EXISTS user_profiles (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户资料主键',
  user_id     BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  nickname    VARCHAR(50)     DEFAULT NULL COMMENT '昵称',
  avatar_url  VARCHAR(255)    DEFAULT NULL COMMENT '头像地址',
  phone       VARCHAR(20)     DEFAULT NULL COMMENT '手机号',
  email       VARCHAR(100)    DEFAULT NULL COMMENT '邮箱',
  major       VARCHAR(100)    DEFAULT NULL COMMENT '专业',
  bio         VARCHAR(500)    DEFAULT NULL COMMENT '个人简介',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户资料表';

CREATE TABLE IF NOT EXISTS wallets (
  user_id         BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  balance         BIGINT          NOT NULL DEFAULT 0 COMMENT '可用余额(分)',
  total_recharged BIGINT          NOT NULL DEFAULT 0 COMMENT '累计充值金额(分)',
  total_consumed  BIGINT          NOT NULL DEFAULT 0 COMMENT '累计消费金额(分)',
  version         INT             NOT NULL DEFAULT 0 COMMENT '乐观锁版本号，防并发扣减',
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='钱包表';

CREATE TABLE IF NOT EXISTS recharge_orders (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '订单主键',
  order_no         VARCHAR(64)     NOT NULL COMMENT '业务订单号',
  user_id          BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  amount           BIGINT          NOT NULL DEFAULT 0 COMMENT '充值金额(分)',
  points           BIGINT          NOT NULL DEFAULT 0 COMMENT '到账积分/点数',
  payment_method   VARCHAR(30)     NOT NULL DEFAULT 'mock' COMMENT '支付方式: alipay / wxpay / bank / mock',
  status           VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT 'pending / paid / failed / cancelled',
  external_trade_no VARCHAR(128)   DEFAULT NULL COMMENT '第三方支付流水号',
  paid_at          DATETIME        DEFAULT NULL COMMENT '支付成功时间',
  created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_order_no (order_no),
  KEY idx_user_created (user_id, created_at),
  KEY idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='充值订单表';

CREATE TABLE IF NOT EXISTS invoices (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '发票主键',
  user_id     BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  amount      BIGINT          NOT NULL DEFAULT 0 COMMENT '开票金额(分)',
  title       VARCHAR(100)    NOT NULL COMMENT '发票抬头',
  type        VARCHAR(20)     NOT NULL DEFAULT 'personal' COMMENT '发票类型: personal / enterprise',
  status      VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态: pending / issued / rejected',
  tax_no      VARCHAR(50)     DEFAULT NULL COMMENT '企业税号',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_user_created (user_id, created_at),
  KEY idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='发票表';

CREATE TABLE IF NOT EXISTS consumption_records (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录主键',
  user_id         BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  task_id         BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 ai_tasks.id',
  model_id        BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 models.id',
  amount          BIGINT          NOT NULL DEFAULT 0 COMMENT '消费金额(分)',
  balance_before  BIGINT          NOT NULL DEFAULT 0 COMMENT '扣费前余额',
  balance_after   BIGINT          NOT NULL DEFAULT 0 COMMENT '扣费后余额',
  status          VARCHAR(20)     NOT NULL DEFAULT 'success' COMMENT 'success / failed / refunded',
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_user_created (user_id, created_at),
  KEY idx_task_id (task_id),
  KEY idx_model_id (model_id),
  KEY idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='消费记录表';

CREATE TABLE IF NOT EXISTS api_keys (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id      BIGINT UNSIGNED NOT NULL COMMENT '逻辑外键 users.id',
  name         VARCHAR(100)    NOT NULL COMMENT 'Key 名称',
  key_prefix   VARCHAR(20)     NOT NULL COMMENT 'Key 前缀',
  key_hash     VARCHAR(255)    NOT NULL COMMENT 'Key 哈希值，仅保存哈希',
  status       VARCHAR(20)     NOT NULL DEFAULT 'enabled' COMMENT 'enabled / disabled / expired',
  use_count    BIGINT          NOT NULL DEFAULT 0 COMMENT '累计调用次数',
  expires_at   DATETIME        DEFAULT NULL COMMENT '过期时间',
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_user_created (user_id, created_at),
  KEY idx_status (status),
  KEY idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='API Key 表';

CREATE TABLE IF NOT EXISTS operation_logs (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id       BIGINT UNSIGNED DEFAULT NULL COMMENT '逻辑外键 users.id，可为空（系统操作）',
  action        VARCHAR(50)     NOT NULL COMMENT '动作名称',
  resource_type VARCHAR(50)     NOT NULL COMMENT '资源类型',
  resource_id   BIGINT UNSIGNED DEFAULT NULL COMMENT '资源主键',
  ip            VARCHAR(45)     DEFAULT NULL COMMENT '客户端 IP',
  detail_json   JSON            DEFAULT NULL COMMENT '详情 JSON',
  created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_user_created (user_id, created_at),
  KEY idx_created_at (created_at),
  KEY idx_resource (resource_type, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='运营操作日志';

-- 说明：
-- 1. wallets.user_id 唯一，balance 禁止为负；充值/扣减必须在事务中处理并使用 SELECT ... FOR UPDATE 或 version 乐观锁。
-- 2. recharge_orders.order_no 唯一，MVP 阶段允许模拟充值，支付状态由后台同步更新。
-- 3. consumption_records 只允许查询，不允许普通用户修改；写入动作由后台服务统一控制，便于审计和结算。
-- 4. api_keys 仅首次生成时返回完整 Key，后续展示必须为 key_prefix + 哈希结果，禁止明文回显。
-- 5. operation_logs 按 created_at 建立索引并按时间保留 180 天，超期归档或清理由后台任务处理。
