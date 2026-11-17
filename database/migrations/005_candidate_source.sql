-- =============================================================
-- 005_candidate_source.sql · 候选人来源表
-- 目标：MySQL 5.7.32+ / 8.x，InnoDB，utf8mb4_unicode_ci
-- 回滚：DROP TABLE IF EXISTS candidate_source;
-- 说明：
--   · 与 applicant.source_type 双轨并存：source_type 是大类（列表筛选），
--     本表承载细粒度渠道（详情展开），不替代旧列
--   · uk_platform_profile 在 platform_profile_id IS NULL 时不生效
--     （MySQL 允许多个 NULL），用于防同一平台同一档案重复入库
--   · raw_payload 用 MEDIUMTEXT（TEXT 上限 64KB），应用层截断至 512KB
--     并置 payload_truncated = 1
--   · applicant_id 与 applicant.id 实际类型一致（BIGINT UNSIGNED），不建外键
--   · 004（历史简历回填）已取消，编号保留不复用
-- =============================================================

USE hr_system;

CREATE TABLE IF NOT EXISTS candidate_source (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  applicant_id        BIGINT UNSIGNED NOT NULL,
  platform            VARCHAR(50)     NOT NULL
                      COMMENT 'jobstreet/facebook/walkin/referral/staff/import/other',
  platform_profile_id VARCHAR(191)    NULL COMMENT '平台侧唯一标识，可为空',
  source_url          VARCHAR(500)    NULL,
  raw_payload         MEDIUMTEXT      NULL COMMENT '原始片段，应用层截断至 512KB',
  payload_truncated   TINYINT         NOT NULL DEFAULT 0,
  first_seen_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_platform_profile (platform, platform_profile_id),
  KEY idx_applicant (applicant_id),
  KEY idx_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  ROW_FORMAT=DYNAMIC COMMENT='候选人来源';

-- 成功标记（必须是最后一句）
INSERT IGNORE INTO schema_version (version, name)
VALUES (5, '005_candidate_source.sql');
