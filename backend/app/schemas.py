"""Pydantic v2 请求/响应模型"""

import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.phone import (
    is_valid_phone as is_valid_phone,
)
from app.utils.phone import (
    normalize_ph_phone,
)
from app.utils.phone import (
    normalize_phone as normalize_phone,
)


def _blank_str_to_none(v: Any) -> Any:
    """将纯空白字符串归一为 None，避免选填字段传空串撞上正则校验"""
    if isinstance(v, str) and not v.strip():
        return None
    return v


# ---------- 通用响应 ----------

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None


# ---------- 员工登录 ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class StaffInfo(BaseModel):
    id: int
    username: str
    real_name: str
    role: str


class LoginData(BaseModel):
    token: str
    staff: StaffInfo


# ---------- 申请人提交 ----------

class ApplicantSubmit(BaseModel):
    """自助/代录提交申请表（字段全量对齐 applicant 表，前端按需逐步开放）"""

    # 隐私同意（必填，落库时间戳用于 RA 10173 合规留痕）
    privacy_agreed: bool = Field(..., description="Whether the privacy policy is accepted. Must be true.")

    # A. 基本身份
    first_name: str = Field(..., min_length=1, max_length=64)
    middle_name: str | None = Field(None, max_length=64)
    last_name: str = Field(..., min_length=1, max_length=64)
    gender: str | None = Field(None, max_length=16, pattern="^(male|female)$")
    birth_date: date | None = None
    nationality: str | None = Field("Filipino", max_length=64)
    marital_status: str | None = Field(None, max_length=16, pattern="^(single|married|widowed|separated|annulled)$")

    # A. 联系方式
    phone: str = Field(..., min_length=1, max_length=32)
    phone_alt: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    address_city: str | None = Field(None, max_length=64)
    address_barangay: str | None = Field(None, max_length=64)
    home_province: str | None = Field(None, max_length=64)

    # E. 社交账号
    fb_profile_url: str | None = Field(None, max_length=255)
    fb_phone: str | None = Field(None, max_length=32)
    fb_name: str | None = Field(None, max_length=128)
    tiktok_username: str | None = Field(None, max_length=64)

    # B. 证件
    id1_type: str | None = Field(None, max_length=64)
    id1_number: str | None = Field(None, max_length=64)
    id2_type: str | None = Field(None, max_length=64)
    id2_number: str | None = Field(None, max_length=64)
    id3_type: str | None = Field(None, max_length=64)
    id3_number: str | None = Field(None, max_length=64)
    has_nbi: bool | None = None
    nbi_valid_until: date | None = None

    # C. 求职意向
    target_job: str | None = Field(None, max_length=128)
    expected_salary: int | None = Field(None, ge=0)
    available_time: str | None = Field(None, max_length=32, pattern="^(anytime|2weeks|1month)$")
    work_type: str | None = Field(None, max_length=32)
    preferred_location: str | None = Field(None, max_length=128)
    live_in_ok: bool | None = None

    # D. 技能与经验
    education: str | None = Field(None, max_length=64)
    skills: list[str] | None = None
    english_level: str | None = Field(None, max_length=16)
    chinese_level: str | None = Field(None, max_length=16)
    last_job: str | None = Field(None, max_length=255)
    work_experience: str | None = None

    # E. 媒体文件
    photo_oss_key: str | None = Field(None, max_length=255)
    video_oss_key: str | None = Field(None, max_length=255)
    resume_oss_key: str | None = Field(None, max_length=255)
    resume_file_name: str | None = Field(None, max_length=255)
    # OSS 直传会话：hr/ 前缀的媒体 key 必须落在该会话签发的 prefix 内
    upload_session_token: str | None = Field(None, max_length=200)

    # E. 来源追踪
    # source_type 由服务端根据登录态判定，不在此声明 —— 客户端传入会被忽略，
    # 防止外部伪造 "staff" 来源刷业绩。
    source_ref: str | None = Field(
        None, max_length=64,
        description="Referral or invite code (letters, numbers, underscore and hyphen only). For staff entries it is overwritten with the staff username by the server.",
    )
    referrer_phone: str | None = Field(None, max_length=32)

    # 自由长备注
    applicant_remark: str | None = None

    # ---------- 校验器 ----------

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        normalized = normalize_ph_phone(v)
        if not normalized:
            raise ValueError("Please enter a valid mobile number (09XXXXXXXXX, 11 digits)")
        return normalized

    @field_validator("phone_alt")
    @classmethod
    def _validate_phone_alt(cls, v: str | None) -> str | None:
        if not v:
            return None
        normalized = normalize_ph_phone(v)
        if not normalized:
            raise ValueError("Please enter a valid backup number (09XXXXXXXXX, 11 digits)")
        return normalized

    @field_validator("source_ref")
    @classmethod
    def _validate_source_ref(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", v):
            raise ValueError("Referral code can only use letters, numbers, _ and - (1-64 characters)")
        return v

    @field_validator("privacy_agreed")
    @classmethod
    def _require_privacy(cls, v: bool) -> bool:
        # 服务端也必须校验：前端勾选框不能作为唯一凭证
        if not v:
            raise ValueError("Please agree to the privacy policy before submitting")
        return v


# ---------- 申请人编辑 ----------

class ApplicantUpdateRequest(BaseModel):
    """后台编辑申请人资料（PATCH，只更新传入的字段）

    刻意不开放：status（走状态流转接口）、salary/employer/hired_date（随 hired 状态更新）、
    source_type/source_ref/created_by（来源归属不可篡改）、privacy_agreed_at/deleted_at（系统字段）
    """

    # A. 基本身份
    first_name: str | None = Field(None, min_length=1, max_length=64)
    middle_name: str | None = Field(None, max_length=64)
    last_name: str | None = Field(None, min_length=1, max_length=64)
    gender: str | None = Field(None, max_length=16, pattern="^(male|female)$")
    birth_date: date | None = None
    nationality: str | None = Field(None, max_length=64)
    marital_status: str | None = Field(None, max_length=16, pattern="^(single|married|widowed|separated|annulled)$")

    # A. 联系方式
    phone: str | None = Field(None, min_length=1, max_length=32)
    phone_alt: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=128)
    address_city: str | None = Field(None, max_length=64)
    address_barangay: str | None = Field(None, max_length=64)
    home_province: str | None = Field(None, max_length=64)

    # E. 社交账号
    fb_profile_url: str | None = Field(None, max_length=255)
    fb_phone: str | None = Field(None, max_length=32)
    fb_name: str | None = Field(None, max_length=128)
    tiktok_username: str | None = Field(None, max_length=64)

    # B. 证件
    id1_type: str | None = Field(None, max_length=64)
    id1_number: str | None = Field(None, max_length=64)
    id2_type: str | None = Field(None, max_length=64)
    id2_number: str | None = Field(None, max_length=64)
    id3_type: str | None = Field(None, max_length=64)
    id3_number: str | None = Field(None, max_length=64)
    has_nbi: bool | None = None
    nbi_valid_until: date | None = None

    # C. 求职意向
    target_job: str | None = Field(None, max_length=128)
    expected_salary: int | None = Field(None, ge=0)
    available_time: str | None = Field(None, max_length=32, pattern="^(anytime|2weeks|1month)$")
    availability: int | None = Field(None, ge=0, le=3)
    available_from: date | None = None
    work_type: str | None = Field(None, max_length=32, pattern="^(fulltime|parttime|temp)$")
    preferred_location: str | None = Field(None, max_length=128)
    intent_tags: str | None = Field(None, max_length=255)
    live_in_ok: bool | None = None

    # D. 技能与经验
    education: str | None = Field(None, max_length=64)
    skills: list[str] | None = None
    english_level: str | None = Field(None, max_length=16, pattern="^(none|basic|fluent)$")
    chinese_level: str | None = Field(None, max_length=16, pattern="^(none|basic|fluent)$")
    last_job: str | None = Field(None, max_length=255)
    work_experience: str | None = None

    # 媒体
    photo_oss_key: str | None = Field(None, max_length=255)
    video_oss_key: str | None = Field(None, max_length=255)
    resume_oss_key: str | None = Field(None, max_length=255)
    resume_file_name: str | None = Field(None, max_length=255)

    # 备注（applicant_remark 前端可见，internal_remark 仅后台）
    applicant_remark: str | None = None
    internal_remark: str | None = None

    @field_validator(
        "middle_name",
        "gender",
        "nationality",
        "marital_status",
        "email",
        "address_city",
        "address_barangay",
        "home_province",
        "fb_profile_url",
        "fb_phone",
        "fb_name",
        "tiktok_username",
        "id1_type",
        "id1_number",
        "id2_type",
        "id2_number",
        "id3_type",
        "id3_number",
        "target_job",
        "available_time",
        "work_type",
        "preferred_location",
        "education",
        "english_level",
        "chinese_level",
        "last_job",
        "work_experience",
        "applicant_remark",
        "internal_remark",
        mode="before",
    )
    @classmethod
    def _normalize_blank_str(cls, v: Any) -> Any:
        return _blank_str_to_none(v)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = normalize_ph_phone(v)
        if not normalized:
            raise ValueError("Invalid mobile number. Use the format 09XXXXXXXXX (11-digit Philippine mobile number).")
        return normalized

    @field_validator("phone_alt")
    @classmethod
    def _validate_phone_alt(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        normalized = normalize_ph_phone(v)
        if not normalized:
            raise ValueError("Invalid alternate mobile number. Use the format 09XXXXXXXXX (11-digit Philippine mobile number).")
        return normalized

    @field_validator("intent_tags")
    @classmethod
    def _normalize_tags(cls, v: str | None) -> str | None:
        """统一小写、逗号分隔、逗号后无空格，最多 10 个（见方案 5.4）"""
        if v is None:
            return None
        tags = [tag.strip().lower() for tag in v.split(",") if tag.strip()]
        # 去重但保持输入顺序，避免 "bpo,cashier,bpo" 这类重复标签入库
        tags = list(dict.fromkeys(tags))
        if len(tags) > 10:
            raise ValueError("At most 10 intent tags are allowed.")
        return ",".join(tags) if tags else None


# ---------- 手机号预检 ----------

class PhoneCheckRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)


# ---------- 申请人详情/列表 ----------

class ApplicantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    middle_name: str | None = None
    last_name: str
    gender: str | None = None
    birth_date: date | None = None
    nationality: str | None = None
    marital_status: str | None = None

    phone: str
    phone_alt: str | None = None
    phone_normalized: str | None = None
    email: str | None = None
    address_city: str | None = None
    address_barangay: str | None = None
    home_province: str | None = None

    fb_profile_url: str | None = None
    fb_phone: str | None = None
    fb_name: str | None = None
    tiktok_username: str | None = None

    id1_type: str | None = None
    id1_number: str | None = None
    id2_type: str | None = None
    id2_number: str | None = None
    id3_type: str | None = None
    id3_number: str | None = None
    has_nbi: bool | None = None
    nbi_valid_until: date | None = None

    target_job: str | None = None
    expected_salary: int | None = None
    available_time: str | None = None
    availability: int = 0
    available_from: date | None = None
    work_type: str | None = None
    preferred_location: str | None = None
    intent_tags: str | None = None
    live_in_ok: bool | None = None

    education: str | None = None
    skills: list[str] | None = None
    english_level: str | None = None
    chinese_level: str | None = None
    last_job: str | None = None
    work_experience: str | None = None

    photo_oss_key: str | None = None
    video_oss_key: str | None = None
    resume_oss_key: str | None = None
    resume_file_name: str | None = None

    source_type: str
    source_ref: str | None = None
    referrer_phone: str | None = None
    applicant_remark: str | None = None

    status: str
    salary: int | None = None
    employer: str | None = None
    hired_date: date | None = None
    internal_remark: str | None = None

    created_by: int | None = None
    privacy_agreed_at: datetime | None = None
    deleted_at: datetime | None = None
    merged_into_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ResumeDocumentOut(BaseModel):
    """详情页展示的多份简历（不含正文，正文不返回给前端）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    file_ext: str
    file_size: int
    extract_state: int
    created_at: datetime


class CandidateSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_profile_id: str | None = None
    source_url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime


class ApplicantDetailOut(ApplicantOut):
    """详情 = 主档 + 多简历 + 来源列表（字段只增不改，保持前端兼容）"""

    resumes: list[ResumeDocumentOut] = []
    sources: list[CandidateSourceOut] = []


class ApplicantListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ApplicantOut]


# ---------- 状态流转 ----------

class StatusUpdateRequest(BaseModel):
    to_status: str = Field(..., pattern="^(new|contacted|interview1|interview2|interview3|hired|lost|rejected)$")
    note: str | None = Field(None, max_length=512)
    # 状态变为 hired 时可同时更新雇佣信息
    salary: int | None = None
    employer: str | None = Field(None, max_length=128)
    hired_date: date | None = None


class StatusHistoryItem(BaseModel):
    """状态流转记录（含操作人姓名，用于时间轴展示）"""
    id: int
    from_status: str | None = None
    to_status: str
    operator_id: int | None = None
    operator_name: str | None = None
    note: str | None = None
    created_at: datetime


# ---------- 联系记录 ----------

class ContactLogCreateRequest(BaseModel):
    channel: str = Field(
        ..., pattern="^(phone|sms|whatsapp|messenger|email|inperson)$",
    )
    result: str = Field(
        ..., pattern="^(reached|no_answer|wrong_number|refused|interview_booked)$",
    )
    note: str | None = Field(None, max_length=500)
    next_follow_at: datetime | None = None


class ContactLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applicant_id: int
    channel: str
    result: str
    note: str | None = None
    operator_id: int | None = None
    operator_name: str | None = None
    next_follow_at: datetime | None = None
    created_at: datetime


class FollowUpItem(BaseModel):
    """今日待跟进（含候选人信息，供列表直接展示）"""

    contact_id: int
    applicant_id: int
    applicant_name: str
    phone: str
    channel: str
    result: str
    note: str | None = None
    next_follow_at: datetime
    operator_name: str | None = None


# ---------- 面试记录 ----------

class InterviewRecordCreateRequest(BaseModel):
    round: int = Field(..., ge=1, le=3)
    interview_at: datetime | None = None
    result: str = Field(..., pattern="^(pass|fail|pending)$")
    comment: str | None = Field(None, max_length=2000)

    @field_validator("comment", mode="before")
    @classmethod
    def _normalize_comment(cls, v: Any) -> Any:
        return _blank_str_to_none(v)


class InterviewRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applicant_id: int
    round: int
    interview_at: datetime | None = None
    result: str | None = None
    comment: str | None = None
    operator_id: int | None = None
    operator_name: str | None = None
    created_at: datetime


# ---------- 员工管理 ----------

class StaffCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=64)
    real_name: str = Field(..., min_length=1, max_length=64)
    role: str = Field("staff", pattern="^(admin|staff)$")


class StaffUpdateRequest(BaseModel):
    real_name: str | None = Field(None, min_length=1, max_length=64)
    role: str | None = Field(None, pattern="^(admin|staff)$")


class StaffPasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=64)


class StaffStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class StaffListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[StaffOut]
