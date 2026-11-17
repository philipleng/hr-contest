-- =============================================================
-- 003_applicant_patch.sql · 申请人主表增量列与索引
-- 目标：MySQL 5.7.32+ / 8.x，InnoDB，utf8mb4_unicode_ci
-- 内容：5 个新列 + updated_at 兜底 + 2 个索引
-- 回滚：
--   DROP INDEX idx_phone_normalized ON applicant;
--   DROP INDEX idx_status_created   ON applicant;
--   ALTER TABLE applicant
--     DROP COLUMN phone_normalized,
--     DROP COLUMN availability,
--     DROP COLUMN available_from,
--     DROP COLUMN intent_tags,
--     DROP COLUMN merged_into_id;
--   注意：updated_at 若迁移前已存在，回滚时不要删除。
-- 说明：
--   · MySQL 5.7 不支持 ADD COLUMN IF NOT EXISTS，全部先查 information_schema
--   · updated_at 必须三步走；本脚本已做存在性判断，可重复执行且不会刷历史值
--   · merged_into_id 与 applicant.id 实际类型一致（BIGINT UNSIGNED），不建外键
-- =============================================================

USE hr_system;

-- -------------------------------------------------------------
-- 1. 普通列（逐列判断，缺哪列补哪列）
-- -------------------------------------------------------------

-- phone_normalized：归一化手机号，仅用于检索与去重提示，phone 列保留原始输入
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'phone_normalized');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN phone_normalized VARCHAR(20) NULL COMMENT ''归一化手机号，仅检索与去重提示'' AFTER phone_alt',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- availability：0未知 1在找工作 2在职 3暂不考虑
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'availability');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN availability TINYINT NOT NULL DEFAULT 0 COMMENT ''0未知 1在找工作 2在职 3暂不考虑'' AFTER available_time',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- available_from：可到岗日期
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'available_from');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN available_from DATE NULL COMMENT ''可到岗日期'' AFTER availability',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- intent_tags：岗位意向标签，小写、逗号分隔、逗号后不加空格，单条最多 10 个
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'intent_tags');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN intent_tags VARCHAR(255) NULL COMMENT ''岗位意向标签，小写逗号分隔'' AFTER preferred_location',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- merged_into_id：重复档案合并后指向保留的主档，不做自动合并
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'merged_into_id');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN merged_into_id BIGINT UNSIGNED NULL COMMENT ''被合并到的主档 ID'' AFTER deleted_at',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- -------------------------------------------------------------
-- 2. updated_at 三步法（仅当列缺失或定义不正确时才执行）
--    先加可空列 → 回填 created_at → 收紧为 NOT NULL + ON UPDATE
-- -------------------------------------------------------------
-- 先判断是否已满足最终定义；缺列、可空、无 ON UPDATE 都算不满足
SET @ua_ok := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'updated_at'
    AND IS_NULLABLE = 'NO'
    AND COLUMN_DEFAULT = 'CURRENT_TIMESTAMP'
    AND EXTRA LIKE '%on update CURRENT_TIMESTAMP%');

-- 2.1 缺列则加可空列（不设默认值，避免历史行被刷成执行时刻）
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND COLUMN_NAME = 'updated_at');
SET @sql := IF(@exist = 0,
  'ALTER TABLE applicant ADD COLUMN updated_at DATETIME NULL COMMENT ''最后更新时间''',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2.2 回填历史值：用 created_at，不用 NOW()
SET @sql := IF(@ua_ok = 0,
  'UPDATE applicant SET updated_at = created_at WHERE updated_at IS NULL',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2.3 收紧定义，交给数据库自动维护
SET @sql := IF(@ua_ok = 0,
  'ALTER TABLE applicant MODIFY updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- -------------------------------------------------------------
-- 3. 新增索引（先查 information_schema.STATISTICS）
-- -------------------------------------------------------------
SET @exist := (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND INDEX_NAME = 'idx_phone_normalized');
SET @sql := IF(@exist = 0,
  'CREATE INDEX idx_phone_normalized ON applicant (phone_normalized)',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exist := (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'applicant'
    AND INDEX_NAME = 'idx_status_created');
SET @sql := IF(@exist = 0,
  'CREATE INDEX idx_status_created ON applicant (status, created_at)',
  'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- -------------------------------------------------------------
-- 4. 成功标记（必须是最后一句）
-- -------------------------------------------------------------
INSERT IGNORE INTO schema_version (version, name)
VALUES (3, '003_applicant_patch.sql');
