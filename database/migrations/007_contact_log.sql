-- =============================================================
-- 007_contact_log.sql · 联系记录表
-- 目标：MySQL 5.7.32+ / 8.x，InnoDB，utf8mb4_unicode_ci
-- 回滚：DROP TABLE IF EXISTS contact_log;
-- 说明：
--   · next_follow_at 是产生行动的关键字段，为空表示无需跟进
--   · operator_id 取当前登录 staff，与 applicant.id 实际类型一致
--     （BIGINT UNSIGNED），不建外键
--   · 006（合并日志）延后，编号保留不复用
-- =============================================================

USE hr_system;

CREATE TABLE IF NOT EXISTS contact_log (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  applicant_id   BIGINT UNSIGNED NOT NULL,
  channel        VARCHAR(20)     NOT NULL
                 COMMENT 'phone/sms/whatsapp/messenger/email/inperson',
  result         VARCHAR(30)     NOT NULL
                 COMMENT 'reached/no_answer/wrong_number/refused/interview_booked',
  note           VARCHAR(500)    NULL,
  operator_id    BIGINT UNSIGNED NULL,
  next_follow_at DATETIME        NULL COMMENT '为空表示无需跟进',
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_applicant_time (applicant_id, created_at),
  KEY idx_next_follow (next_follow_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='联系记录';

-- 成功标记（必须是最后一句）
INSERT IGNORE INTO schema_version (version, name)
VALUES (7, '007_contact_log.sql');
