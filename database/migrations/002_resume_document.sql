-- =============================================================
-- 002_resume_document.sql · 多简历文件表
-- 目标：MySQL 5.7.32+ / 8.x，InnoDB，utf8mb4_unicode_ci
-- 回滚：DROP TABLE IF EXISTS resume_document;
-- 说明：
--   · applicant_id 可空——文件先入库、人后补；待归属队列即 WHERE applicant_id IS NULL
--   · content_hash 普通索引而非唯一键——不同人上传同一份模板简历是合法场景
--   · content_hash 用 ascii + ascii_bin——utf8mb4 下 CHAR(64) 索引占 256 字节，ascii 只需 64
--   · content_hash 允许 NULL——文件缺失时不编造哈希，避免污染去重语义
--   · 主档关联列与 applicant.id 实际类型一致（BIGINT UNSIGNED），不建外键
-- =============================================================

USE hr_system;

CREATE TABLE IF NOT EXISTS resume_document (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  applicant_id  BIGINT UNSIGNED NULL COMMENT '允许为空：文件先入库，人后补',
  oss_key       VARCHAR(255) NOT NULL COMMENT '私有存储相对路径',
  file_name     VARCHAR(255) NOT NULL COMMENT '原始文件名',
  file_ext      VARCHAR(16)  NOT NULL COMMENT '小写扩展名，含点',
  file_size     INT          NOT NULL DEFAULT 0 COMMENT '字节',
  content_hash  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL
                COMMENT 'sha256；文件缺失时为 NULL',
  text_excerpt  MEDIUMTEXT   NULL COMMENT '提取正文，供检索与 AI 抽取',
  extract_state TINYINT      NOT NULL DEFAULT 0
                COMMENT '0待提取 1成功 2失败 3扫描件 4文件缺失',
  source_id     BIGINT UNSIGNED NULL COMMENT '对应 candidate_source.id',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_applicant_created (applicant_id, created_at),
  KEY idx_hash (content_hash),
  KEY idx_extract_state (extract_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  ROW_FORMAT=DYNAMIC COMMENT='简历文件';

INSERT IGNORE INTO schema_version (version, name)
VALUES (2, '002_resume_document.sql');
