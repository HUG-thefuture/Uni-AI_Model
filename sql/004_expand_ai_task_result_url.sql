-- SiliconFlow 的预签名图片 URL 通常超过 VARCHAR(500)，多图结果还会以 JSON 数组保存。
-- 在目标 MySQL 数据库执行一次；该变更不会删除或改写已有任务数据。
ALTER TABLE ai_tasks
    MODIFY COLUMN result_url TEXT NULL COMMENT '文件结果地址或地址数组 JSON';
