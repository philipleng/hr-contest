"""000 · 核心表基线迁移

与 database/schema.sql 的 5 张核心表（0003 增量列之前）严格对齐，
确保空库执行 alembic upgrade head 可完整建表：
applicant / staff / status_history / interview_record / import_batch
"""

import sqlalchemy as sa
from alembic import op

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("applicant"):
        op.execute(
            """
            CREATE TABLE applicant (
              id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              first_name        VARCHAR(64)     NOT NULL COMMENT '名',
              middle_name       VARCHAR(64)     NULL     COMMENT '中间名（菲律宾习惯）',
              last_name         VARCHAR(64)     NOT NULL COMMENT '姓',
              gender            VARCHAR(16)     NULL     COMMENT 'male/female',
              birth_date        DATE            NULL     COMMENT '出生日期',
              nationality       VARCHAR(64)     NULL DEFAULT 'Filipino' COMMENT '国籍',
              marital_status    VARCHAR(16)     NULL     COMMENT 'single/married/widowed/separated/annulled',
              phone             VARCHAR(32)     NOT NULL COMMENT '主手机号（去重键）',
              phone_alt         VARCHAR(32)     NULL     COMMENT '备用手机号',
              email             VARCHAR(128)    NULL     COMMENT '邮箱（选填）',
              address_city      VARCHAR(64)     NULL     COMMENT '现居城市',
              address_barangay  VARCHAR(64)     NULL     COMMENT '现居描笼涯（Barangay）',
              home_province     VARCHAR(64)     NULL     COMMENT '家乡省份',
              fb_profile_url    VARCHAR(255)    NULL     COMMENT 'Facebook 主页链接（选填）',
              fb_phone          VARCHAR(32)     NULL     COMMENT 'FB 绑定手机号（选填，兜底找人）',
              fb_name           VARCHAR(128)    NULL     COMMENT 'FB 昵称（选填，辅助展示）',
              tiktok_username   VARCHAR(64)     NULL     COMMENT 'TikTok @用户名（选填，全局唯一）',
              id1_type          VARCHAR(64)     NULL     COMMENT '证件1类型（自由填/常用选项）',
              id1_number        VARCHAR(64)     NULL     COMMENT '证件1号码',
              id2_type          VARCHAR(64)     NULL     COMMENT '证件2类型',
              id2_number        VARCHAR(64)     NULL     COMMENT '证件2号码',
              id3_type          VARCHAR(64)     NULL     COMMENT '证件3类型',
              id3_number        VARCHAR(64)     NULL     COMMENT '证件3号码',
              has_nbi           TINYINT(1)      NULL     COMMENT '是否有 NBI 无犯罪证明 1有/0无',
              nbi_valid_until   DATE            NULL     COMMENT 'NBI 有效期至',
              target_job        VARCHAR(128)    NULL     COMMENT '意向岗位/工种',
              expected_salary   INT             NULL     COMMENT '期望月薪（PHP）',
              available_time    VARCHAR(32)     NULL     COMMENT '可到岗 anytime/2weeks/1month',
              work_type         VARCHAR(32)     NULL     COMMENT 'fulltime/parttime/temp',
              preferred_location VARCHAR(128)   NULL     COMMENT '可接受工作地点',
              live_in_ok        TINYINT(1)      NULL     COMMENT '是否接受住家 1/0',
              education         VARCHAR(64)     NULL     COMMENT '最高学历',
              skills            JSON            NULL     COMMENT '技能标签数组 ["驾驶","烹饪"]',
              english_level     VARCHAR(16)     NULL     COMMENT 'none/basic/fluent',
              chinese_level     VARCHAR(16)     NULL     COMMENT 'none/basic/fluent',
              last_job          VARCHAR(255)    NULL     COMMENT '最近一份工作及年限',
              work_experience   TEXT            NULL     COMMENT '工作经验简述',
              photo_oss_key     VARCHAR(255)    NULL     COMMENT '照片 OSS 对象键',
              video_oss_key     VARCHAR(255)    NULL     COMMENT '20秒自述视频 OSS 对象键',
              resume_oss_key    VARCHAR(255)    NULL     COMMENT '简历附件 OSS 对象键（PDF/Word/Excel/图片）',
              resume_file_name  VARCHAR(255)    NULL     COMMENT '简历附件原始文件名',
              source_type       VARCHAR(16)     NOT NULL DEFAULT 'self' COMMENT 'self自助/staff代录/referral推荐/import批量',
              source_ref        VARCHAR(64)     NULL     COMMENT '来源标识：工号/推广码',
              referrer_phone    VARCHAR(32)     NULL     COMMENT '推荐人联系方式（选填）',
              applicant_remark  TEXT            NULL     COMMENT '自由备注（前端开放，可贴文字简历）',
              status            VARCHAR(16)     NOT NULL DEFAULT 'new'
                                COMMENT 'new新录入/contacted已联系/interview1/2/3/hired已雇佣/lost失联/rejected不适合',
              salary            INT             NULL     COMMENT '实际月薪 PHP（已雇佣后填）',
              employer          VARCHAR(128)    NULL     COMMENT '雇主（已雇佣后填）',
              hired_date        DATE            NULL     COMMENT '入职日期',
              internal_remark   TEXT            NULL     COMMENT '内部备注（仅后台可见）',
              created_by        BIGINT UNSIGNED NULL     COMMENT '代录员工ID（自助录入为NULL）',
              privacy_agreed_at DATETIME        NULL     COMMENT '隐私政策同意时间（RA 10173 合规留痕）',
              deleted_at        DATETIME        NULL     COMMENT '软删除时间戳（NULL=未删除）',
              created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              INDEX idx_phone (phone),
              INDEX idx_status (status),
              INDEX idx_source (source_type, source_ref),
              INDEX idx_created_at (created_at),
              INDEX idx_name (last_name, first_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='申请人主表'
            """
        )

    if not _has_table("staff"):
        op.execute(
            """
            CREATE TABLE staff (
              id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              username      VARCHAR(64)     NOT NULL UNIQUE COMMENT '登录账号',
              password_hash VARCHAR(128)    NOT NULL COMMENT 'bcrypt 密码哈希',
              real_name     VARCHAR(64)     NOT NULL COMMENT '真实姓名',
              role          VARCHAR(16)     NOT NULL DEFAULT 'staff' COMMENT 'admin/staff',
              status        VARCHAR(16)     NOT NULL DEFAULT 'active' COMMENT 'active/disabled（离职停用不删除）',
              created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='员工账号表'
            """
        )

    if not _has_table("status_history"):
        op.execute(
            """
            CREATE TABLE status_history (
              id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              applicant_id BIGINT UNSIGNED NOT NULL COMMENT '申请人ID',
              from_status  VARCHAR(16)     NULL     COMMENT '原状态',
              to_status    VARCHAR(16)     NOT NULL COMMENT '新状态',
              operator_id  BIGINT UNSIGNED NULL     COMMENT '操作员工ID',
              note         VARCHAR(512)    NULL     COMMENT '变更备注',
              created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              INDEX idx_applicant (applicant_id),
              INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='状态流转记录'
            """
        )

    if not _has_table("interview_record"):
        op.execute(
            """
            CREATE TABLE interview_record (
              id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              applicant_id BIGINT UNSIGNED NOT NULL COMMENT '申请人ID',
              round        TINYINT         NOT NULL COMMENT '面试轮次 1/2/3',
              interview_at DATETIME        NULL     COMMENT '面试时间',
              result       VARCHAR(16)     NULL     COMMENT 'pass/fail/pending',
              comment      TEXT            NULL     COMMENT '面试评价',
              operator_id  BIGINT UNSIGNED NULL     COMMENT '记录人ID',
              created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              INDEX idx_applicant (applicant_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='面试记录'
            """
        )

    if not _has_table("import_batch"):
        op.execute(
            """
            CREATE TABLE import_batch (
              id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              file_name     VARCHAR(255)    NOT NULL COMMENT '导入文件名',
              total_count   INT             NOT NULL DEFAULT 0 COMMENT '总行数',
              success_count INT             NOT NULL DEFAULT 0 COMMENT '成功数',
              fail_count    INT             NOT NULL DEFAULT 0 COMMENT '失败数',
              fail_detail   TEXT            NULL     COMMENT '失败明细（行号+原因）',
              operator_id   BIGINT UNSIGNED NULL     COMMENT '操作人ID',
              created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='批量导入批次'
            """
        )


def downgrade() -> None:
    for table in ("import_batch", "interview_record", "status_history", "staff", "applicant"):
        if _has_table(table):
            op.execute(f"DROP TABLE {table}")
