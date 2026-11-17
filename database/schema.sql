-- =============================================================
-- HR 人力池系统 · 数据库结构 V1.0
-- 数据库：MySQL 5.7.32+ / 8.x，字符集 utf8mb4
-- 说明：所有字段入库（含暂不开放给前端的），前端按需逐步开放
-- =============================================================

USE hr_system;

-- -------------------------------------------------------------
-- 申请人主表
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS applicant (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    -- A. 基本身份
    first_name      VARCHAR(64)  NOT NULL COMMENT '名',
    middle_name     VARCHAR(64)  NULL     COMMENT '中间名（菲律宾习惯）',
    last_name       VARCHAR(64)  NOT NULL COMMENT '姓',
    gender          VARCHAR(16)  NULL     COMMENT 'male/female',
    birth_date      DATE         NULL     COMMENT '出生日期',
    nationality     VARCHAR(64)  NULL DEFAULT 'Filipino' COMMENT '国籍',
    marital_status  VARCHAR(16)  NULL     COMMENT 'single/married/widowed/separated/annulled',

    -- A. 联系方式
    phone           VARCHAR(32)  NOT NULL COMMENT '主手机号（去重键）',
    phone_alt       VARCHAR(32)  NULL     COMMENT '备用手机号',
    phone_normalized VARCHAR(20) NULL     COMMENT '归一化手机号，仅检索与去重提示',
    email           VARCHAR(128) NULL     COMMENT '邮箱（选填）',
    address_city    VARCHAR(64)  NULL     COMMENT '现居城市',
    address_barangay VARCHAR(64) NULL     COMMENT '现居描笼涯（Barangay）',
    home_province   VARCHAR(64)  NULL     COMMENT '家乡省份',

    -- E. 社交账号（全部选填）
    fb_profile_url  VARCHAR(255) NULL     COMMENT 'Facebook 主页链接（选填）',
    fb_phone        VARCHAR(32)  NULL     COMMENT 'FB 绑定手机号（选填，兜底找人）',
    fb_name         VARCHAR(128) NULL     COMMENT 'FB 昵称（选填，辅助展示）',
    tiktok_username VARCHAR(64)  NULL     COMMENT 'TikTok @用户名（选填，全局唯一）',

    -- B. 证件（3 个自由槽位，全部选填）
    id1_type        VARCHAR(64)  NULL     COMMENT '证件1类型（自由填/常用选项）',
    id1_number      VARCHAR(64)  NULL     COMMENT '证件1号码',
    id2_type        VARCHAR(64)  NULL     COMMENT '证件2类型',
    id2_number      VARCHAR(64)  NULL     COMMENT '证件2号码',
    id3_type        VARCHAR(64)  NULL     COMMENT '证件3类型',
    id3_number      VARCHAR(64)  NULL     COMMENT '证件3号码',
    has_nbi         TINYINT(1)   NULL     COMMENT '是否有 NBI 无犯罪证明 1有/0无',
    nbi_valid_until DATE         NULL     COMMENT 'NBI 有效期至',

    -- C. 求职意向
    target_job      VARCHAR(128) NULL     COMMENT '意向岗位/工种',
    expected_salary INT          NULL     COMMENT '期望月薪（PHP）',
    available_time  VARCHAR(32)  NULL     COMMENT '可到岗 anytime/2weeks/1month',
    availability    TINYINT      NOT NULL DEFAULT 0 COMMENT '0未知 1在找工作 2在职 3暂不考虑',
    available_from  DATE         NULL     COMMENT '可到岗日期',
    work_type       VARCHAR(32)  NULL     COMMENT 'fulltime/parttime/temp',
    preferred_location VARCHAR(128) NULL  COMMENT '可接受工作地点',
    intent_tags     VARCHAR(255) NULL     COMMENT '岗位意向标签，小写逗号分隔',
    live_in_ok      TINYINT(1)   NULL     COMMENT '是否接受住家 1/0',

    -- D. 技能与经验
    education       VARCHAR(64)  NULL     COMMENT '最高学历',
    skills          JSON         NULL     COMMENT '技能标签数组 ["驾驶","烹饪"]',
    english_level   VARCHAR(16)  NULL     COMMENT 'none/basic/fluent',
    chinese_level   VARCHAR(16)  NULL     COMMENT 'none/basic/fluent',
    last_job        VARCHAR(255) NULL     COMMENT '最近一份工作及年限',
    work_experience TEXT         NULL     COMMENT '工作经验简述',

    -- E. 媒体文件（OSS key，不存二进制）
    photo_oss_key   VARCHAR(255) NULL     COMMENT '照片 OSS 对象键',
    video_oss_key   VARCHAR(255) NULL     COMMENT '20秒自述视频 OSS 对象键',
    resume_oss_key  VARCHAR(255) NULL     COMMENT '简历附件 OSS 对象键（PDF/Word/Excel/图片）',
    resume_file_name VARCHAR(255) NULL    COMMENT '简历附件原始文件名',

    -- E. 来源追踪
    source_type     VARCHAR(16)  NOT NULL DEFAULT 'self' COMMENT 'self自助/staff代录/referral推荐/import批量',
    source_ref      VARCHAR(64)  NULL     COMMENT '来源标识：工号/推广码',
    referrer_phone  VARCHAR(32)  NULL     COMMENT '推荐人联系方式（选填）',

    -- 自由长备注（申请人或扫楼员工填，可容纳整份文字简历，≥2000英文单词）
    applicant_remark TEXT        NULL     COMMENT '自由备注（前端开放，可贴文字简历）',

    -- F. 状态管理（后台维护，申请人不可见）
    status          VARCHAR(16)  NOT NULL DEFAULT 'new'
                    COMMENT 'new新录入/contacted已联系/interview1/2/3/hired已雇佣/lost失联/rejected不适合',
    salary          INT          NULL     COMMENT '实际月薪 PHP（已雇佣后填）',
    employer        VARCHAR(128) NULL     COMMENT '雇主（已雇佣后填）',
    hired_date      DATE         NULL     COMMENT '入职日期',
    internal_remark TEXT         NULL     COMMENT '内部备注（仅后台可见）',

    -- 系统字段
    created_by      BIGINT UNSIGNED NULL  COMMENT '代录员工ID（自助录入为NULL）',
    privacy_agreed_at DATETIME   NULL     COMMENT '隐私政策同意时间（RA 10173 合规留痕）',
    deleted_at      DATETIME     NULL     COMMENT '软删除时间戳（NULL=未删除）',
    merged_into_id  BIGINT UNSIGNED NULL  COMMENT '被合并到的主档 ID',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_phone (phone),
    INDEX idx_status (status),
    INDEX idx_source (source_type, source_ref),
    INDEX idx_created_at (created_at),
    INDEX idx_name (last_name, first_name),
    INDEX idx_phone_normalized (phone_normalized),
    INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='申请人主表';

-- -------------------------------------------------------------
-- 工作人员/管理员账号表
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staff (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE COMMENT '登录账号',
    password_hash VARCHAR(128) NOT NULL COMMENT 'bcrypt 密码哈希',
    real_name     VARCHAR(64)  NOT NULL COMMENT '真实姓名',
    role          VARCHAR(16)  NOT NULL DEFAULT 'staff' COMMENT 'admin/staff',
    status        VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active/disabled（离职停用不删除）',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工账号表';

-- -------------------------------------------------------------
-- 状态流转历史表
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS status_history (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    applicant_id BIGINT UNSIGNED NOT NULL COMMENT '申请人ID',
    from_status  VARCHAR(16)     NULL     COMMENT '原状态',
    to_status    VARCHAR(16)     NOT NULL COMMENT '新状态',
    operator_id  BIGINT UNSIGNED NULL     COMMENT '操作员工ID',
    note         VARCHAR(512)    NULL     COMMENT '变更备注',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_applicant (applicant_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='状态流转记录';

-- -------------------------------------------------------------
-- 面试记录表
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interview_record (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    applicant_id BIGINT UNSIGNED NOT NULL COMMENT '申请人ID',
    round        TINYINT         NOT NULL COMMENT '面试轮次 1/2/3',
    interview_at DATETIME        NULL     COMMENT '面试时间',
    result       VARCHAR(16)     NULL     COMMENT 'pass/fail/pending',
    comment      TEXT            NULL     COMMENT '面试评价',
    operator_id  BIGINT UNSIGNED NULL     COMMENT '记录人ID',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_applicant (applicant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='面试记录';

-- -------------------------------------------------------------
-- 批量导入批次表
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_batch (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    file_name     VARCHAR(255) NOT NULL COMMENT '导入文件名',
    total_count   INT          NOT NULL DEFAULT 0 COMMENT '总行数',
    success_count INT          NOT NULL DEFAULT 0 COMMENT '成功数',
    fail_count    INT          NOT NULL DEFAULT 0 COMMENT '失败数',
    fail_detail   TEXT         NULL     COMMENT '失败明细（行号+原因）',
    operator_id   BIGINT UNSIGNED NULL  COMMENT '操作人ID',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='批量导入批次';

-- -------------------------------------------------------------
-- V1.2 新增：迁移执行日志（见 database/migrations/001_schema_version.sql）
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version    INT          NOT NULL COMMENT '迁移序号，与脚本文件名前缀一致',
    name       VARCHAR(100) NOT NULL COMMENT '脚本文件名',
    applied_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='迁移执行日志';

-- -------------------------------------------------------------
-- V1.2 新增：多简历文件表（见 database/migrations/002_resume_document.sql）
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resume_document (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    applicant_id  BIGINT UNSIGNED NULL     COMMENT '允许为空：文件先入库，人后补',
    oss_key       VARCHAR(255)    NOT NULL COMMENT '私有存储相对路径',
    file_name     VARCHAR(255)    NOT NULL COMMENT '原始文件名',
    file_ext      VARCHAR(16)     NOT NULL COMMENT '小写扩展名，含点',
    file_size     INT             NOT NULL DEFAULT 0 COMMENT '字节',
    content_hash  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL
                  COMMENT 'sha256；文件缺失时为 NULL',
    text_excerpt  MEDIUMTEXT      NULL     COMMENT '提取正文，供检索与 AI 抽取',
    extract_state TINYINT         NOT NULL DEFAULT 0
                  COMMENT '0待提取 1成功 2失败 3扫描件 4文件缺失',
    source_id     BIGINT UNSIGNED NULL     COMMENT '对应 candidate_source.id',
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_applicant_created (applicant_id, created_at),
    KEY idx_hash (content_hash),
    KEY idx_extract_state (extract_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  ROW_FORMAT=DYNAMIC COMMENT='简历文件';

-- -------------------------------------------------------------
-- V1.2 新增：候选人来源表（见 database/migrations/005_candidate_source.sql）
-- -------------------------------------------------------------
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

-- -------------------------------------------------------------
-- V1.2 新增：联系记录表（见 database/migrations/007_contact_log.sql）
-- -------------------------------------------------------------
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

-- -------------------------------------------------------------
-- 已有库升级（建表脚本用 IF NOT EXISTS，不会给旧表补新列）
-- V1.1 新增：申请人隐私同意时间（RA 10173 合规留痕）
--   ALTER TABLE applicant
--     ADD COLUMN privacy_agreed_at DATETIME NULL
--     COMMENT '隐私政策同意时间（RA 10173 合规留痕）' AFTER created_by;
-- V1.2 新增：以上 5 列 + 2 索引的增量升级脚本见
--   database/migrations/003_applicant_patch.sql（含可重复执行的判断逻辑）
-- -------------------------------------------------------------
