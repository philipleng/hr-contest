-- =============================================================
-- 001_schema_version.sql · 迁移执行日志表
-- 目标：MySQL 5.7.32+ / 8.x，InnoDB，utf8mb4_unicode_ci
-- 回滚：DROP TABLE IF EXISTS schema_version;
-- 纪律：版本号写入必须是脚本最后一句（DDL 不在事务内）
-- =============================================================

USE hr_system;

CREATE TABLE IF NOT EXISTS schema_version (
  version    INT          NOT NULL COMMENT '迁移序号，与脚本文件名前缀一致',
  name       VARCHAR(100) NOT NULL COMMENT '脚本文件名',
  applied_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='迁移执行日志';

-- 可重复执行：重复跑脚本时不报主键冲突
INSERT IGNORE INTO schema_version (version, name)
VALUES (1, '001_schema_version.sql');
