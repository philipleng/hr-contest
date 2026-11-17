"""SQLAlchemy 2.0 数据模型 —— 表结构的唯一来源

迁移由 Alembic 管理（backend/alembic/versions/），database/schema.sql 仅作初始参考。
不使用 create_all。
"""

from datetime import date, datetime

from sqlalchemy import INT, JSON, BigInteger, Date, DateTime, Index, String, Text, func
from sqlalchemy.dialects.mysql import CHAR, MEDIUMTEXT, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.tz import now_local


class Base(DeclarativeBase):
    pass


class Applicant(Base):
    __tablename__ = "applicant"
    __table_args__ = (
        Index("idx_phone", "phone"),
        Index("idx_phone_normalized", "phone_normalized"),
        Index("idx_status", "status"),
        Index("idx_status_created", "status", "created_at"),
        Index("idx_source", "source_type", "source_ref"),
        Index("idx_created_at", "created_at"),
        Index("idx_name", "last_name", "first_name"),
        {"comment": "申请人主表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # A. 基本身份
    first_name: Mapped[str] = mapped_column(String(64), comment="名")
    middle_name: Mapped[str | None] = mapped_column(String(64), comment="中间名（菲律宾习惯）")
    last_name: Mapped[str] = mapped_column(String(64), comment="姓")
    gender: Mapped[str | None] = mapped_column(String(16), comment="male/female")
    birth_date: Mapped[date | None] = mapped_column(Date, comment="出生日期")
    nationality: Mapped[str | None] = mapped_column(String(64), default="Filipino", comment="国籍")
    marital_status: Mapped[str | None] = mapped_column(String(16), comment="single/married/widowed/separated/annulled")

    # A. 联系方式
    phone: Mapped[str] = mapped_column(String(32), comment="主手机号（去重键）")
    phone_alt: Mapped[str | None] = mapped_column(String(32), comment="备用手机号")
    phone_normalized: Mapped[str | None] = mapped_column(
        String(20), comment="归一化手机号，仅检索与去重提示"
    )
    email: Mapped[str | None] = mapped_column(String(128), comment="邮箱（选填）")
    address_city: Mapped[str | None] = mapped_column(String(64), comment="现居城市")
    address_barangay: Mapped[str | None] = mapped_column(String(64), comment="现居描笼涯（Barangay）")
    home_province: Mapped[str | None] = mapped_column(String(64), comment="家乡省份")

    # E. 社交账号（全部选填）
    fb_profile_url: Mapped[str | None] = mapped_column(String(255), comment="Facebook 主页链接")
    fb_phone: Mapped[str | None] = mapped_column(String(32), comment="FB 绑定手机号（兜底找人）")
    fb_name: Mapped[str | None] = mapped_column(String(128), comment="FB 昵称（辅助展示）")
    tiktok_username: Mapped[str | None] = mapped_column(String(64), comment="TikTok @用户名（全局唯一）")

    # B. 证件（3 个自由槽位，全部选填）
    id1_type: Mapped[str | None] = mapped_column(String(64), comment="证件1类型（自由填/常用选项）")
    id1_number: Mapped[str | None] = mapped_column(String(64), comment="证件1号码")
    id2_type: Mapped[str | None] = mapped_column(String(64), comment="证件2类型")
    id2_number: Mapped[str | None] = mapped_column(String(64), comment="证件2号码")
    id3_type: Mapped[str | None] = mapped_column(String(64), comment="证件3类型")
    id3_number: Mapped[str | None] = mapped_column(String(64), comment="证件3号码")
    has_nbi: Mapped[bool | None] = mapped_column(TINYINT(1), comment="是否有 NBI 无犯罪证明 1有/0无")
    nbi_valid_until: Mapped[date | None] = mapped_column(Date, comment="NBI 有效期至")

    # C. 求职意向
    target_job: Mapped[str | None] = mapped_column(String(128), comment="意向岗位/工种")
    expected_salary: Mapped[int | None] = mapped_column(INT, comment="期望月薪（PHP）")
    available_time: Mapped[str | None] = mapped_column(String(32), comment="可到岗 anytime/2weeks/1month")
    availability: Mapped[int] = mapped_column(
        TINYINT, default=0, comment="0未知 1在找工作 2在职 3暂不考虑"
    )
    available_from: Mapped[date | None] = mapped_column(Date, comment="可到岗日期")
    work_type: Mapped[str | None] = mapped_column(String(32), comment="fulltime/parttime/temp")
    preferred_location: Mapped[str | None] = mapped_column(String(128), comment="可接受工作地点")
    intent_tags: Mapped[str | None] = mapped_column(
        String(255), comment="岗位意向标签，小写逗号分隔"
    )
    live_in_ok: Mapped[bool | None] = mapped_column(TINYINT(1), comment="是否接受住家 1/0")

    # D. 技能与经验
    education: Mapped[str | None] = mapped_column(String(64), comment="最高学历")
    skills: Mapped[list | None] = mapped_column(JSON, comment='技能标签数组 ["驾驶","烹饪"]')
    english_level: Mapped[str | None] = mapped_column(String(16), comment="none/basic/fluent")
    chinese_level: Mapped[str | None] = mapped_column(String(16), comment="none/basic/fluent")
    last_job: Mapped[str | None] = mapped_column(String(255), comment="最近一份工作及年限")
    work_experience: Mapped[str | None] = mapped_column(Text, comment="工作经验简述")

    # E. 媒体文件（OSS key，不存二进制）
    photo_oss_key: Mapped[str | None] = mapped_column(String(255), comment="照片 OSS 对象键")
    video_oss_key: Mapped[str | None] = mapped_column(String(255), comment="20秒自述视频 OSS 对象键")
    resume_oss_key: Mapped[str | None] = mapped_column(String(255), comment="简历附件 OSS 对象键（PDF/Word/Excel/图片）")
    resume_file_name: Mapped[str | None] = mapped_column(String(255), comment="简历附件原始文件名")

    # E. 来源追踪
    source_type: Mapped[str] = mapped_column(String(16), default="self", comment="self自助/staff代录/referral推荐/import批量")
    source_ref: Mapped[str | None] = mapped_column(String(64), comment="来源标识：工号/推广码")
    referrer_phone: Mapped[str | None] = mapped_column(String(32), comment="推荐人联系方式（选填）")

    # 自由长备注（申请人或扫楼员工填，可容纳整份文字简历）
    applicant_remark: Mapped[str | None] = mapped_column(Text, comment="自由备注（前端开放，可贴文字简历）")

    # F. 状态管理（后台维护，申请人不可见）
    status: Mapped[str] = mapped_column(
        String(16), default="new",
        comment="new新录入/contacted已联系/interview1/2/3/hired已雇佣/lost失联/rejected不适合",
    )
    salary: Mapped[int | None] = mapped_column(INT, comment="实际月薪 PHP（已雇佣后填）")
    employer: Mapped[str | None] = mapped_column(String(128), comment="雇主（已雇佣后填）")
    hired_date: Mapped[date | None] = mapped_column(Date, comment="入职日期")
    internal_remark: Mapped[str | None] = mapped_column(Text, comment="内部备注（仅后台可见）")

    # 系统字段
    created_by: Mapped[int | None] = mapped_column(BigInteger, comment="代录员工ID（自助录入为NULL）")
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, comment="隐私政策同意时间（RA 10173 合规留痕）")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, comment="软删除时间戳（NULL=未删除）")
    merged_into_id: Mapped[int | None] = mapped_column(
        BigInteger, comment="被合并到的主档 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_local,
        onupdate=now_local,
        server_default=func.now(),
        server_onupdate=func.now(),
    )


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = {"comment": "员工账号表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录账号")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt 密码哈希")
    real_name: Mapped[str] = mapped_column(String(64), comment="真实姓名")
    role: Mapped[str] = mapped_column(String(16), default="staff", comment="admin/staff")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="active/disabled（离职停用不删除）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_local,
        onupdate=now_local,
        server_default=func.now(),
        server_onupdate=func.now(),
    )


class StatusHistory(Base):
    __tablename__ = "status_history"
    __table_args__ = (
        Index("idx_applicant", "applicant_id"),
        Index("idx_created_at", "created_at"),
        {"comment": "状态流转记录"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(BigInteger, comment="申请人ID")
    from_status: Mapped[str | None] = mapped_column(String(16), comment="原状态")
    to_status: Mapped[str] = mapped_column(String(16), comment="新状态")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, comment="操作员工ID")
    note: Mapped[str | None] = mapped_column(String(512), comment="变更备注")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )


class InterviewRecord(Base):
    __tablename__ = "interview_record"
    __table_args__ = (
        Index("idx_applicant", "applicant_id"),
        {"comment": "面试记录"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(BigInteger, comment="申请人ID")
    round: Mapped[int] = mapped_column(TINYINT, comment="面试轮次 1/2/3")
    interview_at: Mapped[datetime | None] = mapped_column(DateTime, comment="面试时间")
    result: Mapped[str | None] = mapped_column(String(16), comment="pass/fail/pending")
    comment: Mapped[str | None] = mapped_column(Text, comment="面试评价")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, comment="记录人ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = {"comment": "批量导入批次"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), comment="导入文件名")
    total_count: Mapped[int] = mapped_column(INT, default=0, comment="总行数")
    success_count: Mapped[int] = mapped_column(INT, default=0, comment="成功数")
    fail_count: Mapped[int] = mapped_column(INT, default=0, comment="失败数")
    fail_detail: Mapped[str | None] = mapped_column(Text, comment="失败明细（行号+原因）")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, comment="操作人ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )


class ResumeDocument(Base):
    """多简历文件：一个人可挂多份，文件可先入库、人后补"""

    __tablename__ = "resume_document"
    __table_args__ = (
        Index("idx_applicant_created", "applicant_id", "created_at"),
        Index("idx_hash", "content_hash"),
        Index("idx_extract_state", "extract_state"),
        {"comment": "简历文件"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int | None] = mapped_column(
        BigInteger, comment="允许为空：文件先入库，人后补"
    )
    oss_key: Mapped[str] = mapped_column(String(255), comment="私有存储相对路径")
    file_name: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    file_ext: Mapped[str] = mapped_column(String(16), comment="小写扩展名，含点")
    file_size: Mapped[int] = mapped_column(INT, default=0, comment="字节")
    content_hash: Mapped[str | None] = mapped_column(
        String(64).with_variant(CHAR(64, charset="ascii", collation="ascii_bin"), "mysql"),
        comment="sha256；文件缺失时为 NULL",
    )
    text_excerpt: Mapped[str | None] = mapped_column(
        Text().with_variant(MEDIUMTEXT(), "mysql"),
        comment="提取正文，供检索与 AI 抽取",
    )
    extract_state: Mapped[int] = mapped_column(
        TINYINT, default=0, comment="0待提取 1成功 2失败 3扫描件 4文件缺失"
    )
    source_id: Mapped[int | None] = mapped_column(BigInteger, comment="对应 candidate_source.id")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_local,
        onupdate=now_local,
        server_default=func.now(),
        server_onupdate=func.now(),
    )


class CandidateSource(Base):
    """候选人来源：细粒度渠道，与 applicant.source_type 双轨并存"""

    __tablename__ = "candidate_source"
    __table_args__ = (
        Index("uk_platform_profile", "platform", "platform_profile_id", unique=True),
        Index("idx_applicant", "applicant_id"),
        Index("idx_platform", "platform"),
        {"comment": "候选人来源"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(BigInteger)
    platform: Mapped[str] = mapped_column(String(50), comment="来源平台")
    platform_profile_id: Mapped[str | None] = mapped_column(
        String(191), comment="平台侧唯一标识，可为空"
    )
    source_url: Mapped[str | None] = mapped_column(String(500))
    raw_payload: Mapped[str | None] = mapped_column(
        Text().with_variant(MEDIUMTEXT(), "mysql"),
        comment="原始片段，应用层截断至 512KB",
    )
    payload_truncated: Mapped[int] = mapped_column(TINYINT, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )


class ContactLog(Base):
    """联系记录：每次触达与下次跟进"""

    __tablename__ = "contact_log"
    __table_args__ = (
        Index("idx_applicant_time", "applicant_id", "created_at"),
        Index("idx_next_follow", "next_follow_at"),
        {"comment": "联系记录"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(BigInteger)
    channel: Mapped[str] = mapped_column(
        String(20), comment="phone/sms/whatsapp/messenger/email/inperson"
    )
    result: Mapped[str] = mapped_column(
        String(30), comment="reached/no_answer/wrong_number/refused/interview_booked"
    )
    note: Mapped[str | None] = mapped_column(String(500))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    next_follow_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="为空表示无需跟进"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now()
    )
