"""申请人相关 API：自助/代录提交、列表、详情、状态流转"""

import logging
import mimetypes
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Applicant,
    CandidateSource,
    ContactLog,
    InterviewRecord,
    ResumeDocument,
    Staff,
    StatusHistory,
)
from app.routers.oss import PRIVATE_UPLOAD_DIR
from app.schemas import (
    ApiResponse,
    ApplicantDetailOut,
    ApplicantListData,
    ApplicantOut,
    ApplicantSubmit,
    ApplicantUpdateRequest,
    CandidateSourceOut,
    ContactLogCreateRequest,
    ContactLogOut,
    InterviewRecordCreateRequest,
    InterviewRecordOut,
    PhoneCheckRequest,
    ResumeDocumentOut,
    StatusHistoryItem,
    StatusUpdateRequest,
)
from app.utils.auth_deps import get_current_staff, get_optional_staff, require_admin
from app.utils.media_token import sign_media_token
from app.utils.phone import normalize_ph_phone, normalize_phone
from app.utils.ratelimit import rate_limit
from app.utils.tz import day_range, day_start, next_day_start, now_local, today_local
from app.utils.upload_session import verify_upload_session

router = APIRouter(prefix="/applicant", tags=["applicant"])

logger = logging.getLogger(__name__)


def _validate_media_keys(payload: dict, session_token: str | None) -> None:
    """校验 photo/video/resume key 的来源

    - local/ 与 hr/ 均拒绝包含 '..' 或 '\\' 的路径穿越字符
    - local/：仅允许合法相对路径格式
    - hr/：必须带有效上传会话，且 key 落在该会话前缀内
    - resume_oss_key：必须以 'resume/' 开头且后跟非空相对路径，拒绝 '..' 与 '\\'
    """
    prefix = verify_upload_session(session_token)
    for field in ("photo_oss_key", "video_oss_key"):
        key = payload.get(field)
        if not key:
            continue
        if ".." in key or "\\" in key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid {field}.")
        if key.startswith("local/"):
            continue
        if key.startswith("hr/"):
            if prefix is None or not key.startswith(prefix):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Upload session is missing or does not match the media key.",
                )
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid {field}.")

    resume_key = payload.get("resume_oss_key")
    if resume_key:
        if ".." in resume_key or "\\" in resume_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid resume_oss_key.")
        if not resume_key.startswith("resume/") or len(resume_key) <= len("resume/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid resume_oss_key.")


def _resolve_resume_path(resume_key: str) -> str | None:
    """在 PRIVATE_UPLOAD_DIR/resume 根目录下安全解析真实文件路径，防路径穿越"""
    if not resume_key or not resume_key.startswith("resume/"):
        return None
    resume_root = os.path.realpath(os.path.join(PRIVATE_UPLOAD_DIR, "resume"))
    path = os.path.realpath(os.path.join(resume_root, resume_key.removeprefix("resume/")))
    if not path.startswith(resume_root + os.sep) or not os.path.isfile(path):
        return None
    return path


def _resolve_resume_file_size(resume_key: str) -> int:
    """解析本地私有简历文件的真实字节数，不存在或路径非法时返回 0"""
    path = _resolve_resume_path(resume_key)
    return os.path.getsize(path) if path else 0


def _add_resume_document(
    db: Session,
    applicant_id: int,
    resume_key: str,
    resume_name: str | None,
) -> None:
    """写入一条 ResumeDocument 记录（含本地真实 file_size）"""
    file_name = resume_name or os.path.basename(resume_key)
    file_ext = (
        os.path.splitext(file_name)[1].lower()
        or os.path.splitext(resume_key)[1].lower()
    )
    db.add(ResumeDocument(
        applicant_id=applicant_id,
        oss_key=resume_key,
        file_name=file_name,
        file_ext=file_ext,
        file_size=_resolve_resume_file_size(resume_key),
        content_hash=None,
        extract_state=0,
    ))


# ------------------------------------------------------------------
# 提交申请（免登录，带 token 则为扫楼代录）
# ------------------------------------------------------------------

class SubmitResult(BaseModel):
    applicant_id: int


@router.post("/submit", response_model=ApiResponse)
def submit(
    data: ApplicantSubmit,
    request: Request,
    db: Session = Depends(get_db),
    staff: Staff | None = Depends(get_optional_staff),
):
    # 限流只针对匿名流量：扫楼代录（带 JWT）不限次数
    if staff is None:
        rate_limit(request, "applicant_submit", max_times=5, window=60)

    payload = data.model_dump()
    session_token = payload.pop("upload_session_token", None)
    _validate_media_keys(payload, session_token)

    # 隐私同意：由服务端按业务时区打时间戳，不信任客户端传值（Pydantic 已强制为 True）
    payload.pop("privacy_agreed", None)
    payload["privacy_agreed_at"] = now_local()

    # 来源字段一律由服务端判定，忽略客户端传入的 source_type
    if staff is not None:
        payload.update(
            source_type="staff",
            source_ref=staff.username,
            created_by=staff.id,
        )
    else:
        ref = data.source_ref
        payload.update(
            source_type="referral" if ref else "self",
            source_ref=ref,
            created_by=None,
        )

    # 手机号柔性去重（手机号已由 Pydantic 校验器归一化）
    existing = db.scalar(
        select(Applicant).where(
            Applicant.phone == payload["phone"],
            Applicant.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This mobile number has already applied. Please contact our staff if you need to update it.",
        )

    # 简历改为单写 resume_document（旧列 resume_oss_key 不再写入）
    resume_key = payload.pop("resume_oss_key", None)
    resume_name = payload.pop("resume_file_name", None)
    # phone_normalized 只存确认是移动号的值，座机等返回 None
    payload["phone_normalized"] = normalize_ph_phone(payload["phone"])

    applicant = Applicant(**payload)
    db.add(applicant)
    db.flush()  # 拿到自增 ID，供状态流水、简历、来源使用

    # 首次录入即写入状态流水，保证全生命周期可追溯
    db.add(StatusHistory(
        applicant_id=applicant.id,
        from_status=None,
        to_status="new",
        operator_id=staff.id if staff else None,
        note="First entry",
    ))

    # 来源表从第一天起就有数据：扫楼代录记 staff，自助提交记 self
    db.add(CandidateSource(
        applicant_id=applicant.id,
        platform="staff" if staff else "self",
    ))

    if resume_key:
        _add_resume_document(db, applicant.id, resume_key, resume_name)

    db.commit()
    db.refresh(applicant)

    return ApiResponse(
        message="Submitted.",
        data=SubmitResult(applicant_id=applicant.id),
    )


# ------------------------------------------------------------------
# 手机号预检（固定路径必须写在 /{applicant_id} 之前）
# ------------------------------------------------------------------

@router.post("/check-phone", response_model=ApiResponse)
def check_phone(
    data: PhoneCheckRequest,
    request: Request,
    db: Session = Depends(get_db),
    _staff: Staff | None = Depends(get_optional_staff),
):
    """提交前预检手机号是否已存在

    只返回布尔值，不返回任何申请人信息，避免被当成「查号」接口拖库。
    带 token 时顺带校验 token：过期/停用会在这里就返回 401，避免前端把照片视频传完才发现登录失效。
    """
    # 限流只针对匿名流量：扫楼代录（带 JWT）不限次数
    if _staff is None:
        rate_limit(request, "applicant_check_phone", max_times=20, window=60)

    phone = normalize_ph_phone(data.phone)
    if not phone:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please enter a valid mobile number (09XXXXXXXXX, 11 digits)",
        )

    exists = db.scalar(
        select(Applicant.id).where(
            Applicant.phone == phone,
            Applicant.deleted_at.is_(None),
        )
    ) is not None

    return ApiResponse(data={"exists": exists})


# ------------------------------------------------------------------
# 列表筛选与排序的公共逻辑（列表、导出共用）
# ------------------------------------------------------------------

# 排序白名单：前端只能传这些键，避免把用户输入直接拼进 ORDER BY
SORT_COLUMNS = {
    "id": (Applicant.id,),
    "name": (Applicant.last_name, Applicant.first_name),
    "birth_date": (Applicant.birth_date,),
    "created_at": (Applicant.created_at,),
    "updated_at": (Applicant.updated_at,),
}


def _years_ago(today: date, years: int) -> date:
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        # 2 月 29 日换算到非闰年时退到 2 月 28 日
        return today.replace(year=today.year - years, day=28)


def apply_demographic_filters(
    stmt,
    gender: str | None,
    age_min: int | None,
    age_max: int | None,
):
    """性别 / 年龄区间筛选（列表与导出共用）

    年龄不做 YEAR() 计算，改写为 birth_date 闭区间：MySQL 5.7 没有函数索引，
    对列做函数运算会退化成全表扫描；闭区间还能吃到 idx_birth_date。
    """
    if gender == "unspecified":
        stmt = stmt.where(Applicant.gender.is_(None))
    elif gender:
        stmt = stmt.where(Applicant.gender == gender)

    if age_min is None and age_max is None:
        return stmt

    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "age_min cannot be greater than age_max.",
        )

    today = today_local()
    # 没填生日的人无法判断年龄，区间筛选时排除，避免被当成 0 岁混进结果
    stmt = stmt.where(Applicant.birth_date.is_not(None))
    if age_max is not None:
        stmt = stmt.where(Applicant.birth_date > _years_ago(today, age_max + 1))
    if age_min is not None:
        stmt = stmt.where(Applicant.birth_date <= _years_ago(today, age_min))
    return stmt


def apply_applicant_filters(
    stmt,
    *,
    status_filter: str | None = None,
    source_type: str | None = None,
    availability: int | None = None,
    intent_tag: str | None = None,
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    new_today: bool = False,
    gender: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
):
    """申请人列表与导出共用的筛选条件（保留 Asia/Manila 日期闭区间与跨方言标签匹配）"""
    if status_filter:
        stmt = stmt.where(Applicant.status == status_filter)
    if source_type:
        stmt = stmt.where(Applicant.source_type == source_type)
    if availability is not None:
        stmt = stmt.where(Applicant.availability == availability)
    if intent_tag:
        # 跨方言等价词边界匹配：MySQL 编译为 concat(',', intent_tags, ',')，SQLite 编译为 ||
        # intent_tag 已受 ^[a-z0-9-]{1,32}$ 约束，不含逗号或通配符
        stmt = stmt.where(
            (literal(",") + Applicant.intent_tags + literal(",")).like(f"%,{intent_tag},%")
        )

    if keyword:
        raw = keyword.strip()
        like = f"%{raw}%"
        conditions = [
            Applicant.first_name.like(like),
            Applicant.last_name.like(like),
            Applicant.phone.like(like),
        ]
        # 手机号搜索归一化：输入 0917-123-4567 也能命中库里的 09171234567
        normalized = normalize_phone(raw)
        if normalized and normalized != raw:
            conditions.append(Applicant.phone.like(f"%{normalized}%"))
        stmt = stmt.where(or_(*conditions))

    if start_date:
        stmt = stmt.where(Applicant.created_at >= day_start(start_date))
    if end_date:
        stmt = stmt.where(Applicant.created_at < next_day_start(end_date))
    if new_today:
        day_begin, day_end = day_range()
        stmt = stmt.where(Applicant.created_at >= day_begin, Applicant.created_at < day_end)

    return apply_demographic_filters(stmt, gender, age_min, age_max)


def apply_sort(stmt, sort_by: str, order: str):
    """按白名单排序，附加主键兜底保证分页顺序稳定"""
    columns = SORT_COLUMNS[sort_by]
    if order == "asc":
        ordered = [c.asc() for c in columns]
    else:
        ordered = [c.desc() for c in columns]
    if sort_by == "birth_date":
        # 没填生日的人固定排最后：MySQL 在 ASC 时把 NULL 排最前，
        # 否则「按年龄排序」会先看到一堆空值，像是坏了
        ordered.insert(0, Applicant.birth_date.is_(None).asc())
    if sort_by != "id":
        ordered.append(Applicant.id.desc())
    return stmt.order_by(*ordered)


# ------------------------------------------------------------------
# 列表（固定路径必须写在 /{applicant_id} 之前）
# ------------------------------------------------------------------

@router.get("/list", response_model=ApiResponse)
def list_applicants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(new|contacted|interview1|interview2|interview3|hired|lost|rejected)$",
    ),
    source_type: str | None = Query(
        None,
        pattern="^(self|staff|referral|import)$",
    ),
    availability: int | None = Query(None, ge=0, le=3, description="0未知 1在找工作 2在职 3暂不考虑"),
    intent_tag: str | None = Query(
        None, pattern="^[a-z0-9-]{1,32}$", description="岗位意向标签，如 bpo",
    ),
    keyword: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    new_today: bool = Query(False, description="Only show new entries from today"),
    gender: str | None = Query(
        None,
        pattern="^(male|female|unspecified)$",
        description="male / female / unspecified (未填写)",
    ),
    age_min: int | None = Query(None, ge=0, le=120),
    age_max: int | None = Query(None, ge=0, le=120),
    sort_by: str = Query("created_at", pattern="^(id|name|birth_date|created_at|updated_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    stmt = select(Applicant).where(Applicant.deleted_at.is_(None))
    stmt = apply_applicant_filters(
        stmt,
        status_filter=status_filter,
        source_type=source_type,
        availability=availability,
        intent_tag=intent_tag,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        new_today=new_today,
        gender=gender,
        age_min=age_min,
        age_max=age_max,
    )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = apply_sort(stmt, sort_by, order).offset((page - 1) * page_size).limit(page_size)
    rows = db.scalars(stmt).all()

    return ApiResponse(data=ApplicantListData(
        total=total,
        page=page,
        page_size=page_size,
        items=[ApplicantOut.model_validate(r) for r in rows],
    ))


@router.get("/stats/today", response_model=ApiResponse)
def today_stats(
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    day_begin, day_end = day_range()
    today_filter = and_(Applicant.created_at >= day_begin, Applicant.created_at < day_end)

    today_total = db.scalar(
        select(func.count()).select_from(Applicant).where(
            Applicant.deleted_at.is_(None), today_filter,
        )
    ) or 0

    today_new = db.scalar(
        select(func.count()).select_from(Applicant).where(
            Applicant.deleted_at.is_(None), today_filter, Applicant.status == "new",
        )
    ) or 0

    all_total = db.scalar(
        select(func.count()).select_from(Applicant).where(Applicant.deleted_at.is_(None))
    ) or 0

    return ApiResponse(data={
        "today_total": today_total,
        "today_pending": today_new,
        "total": all_total,
    })


# ------------------------------------------------------------------
# 详情与状态流转（动态路径放最后）
# ------------------------------------------------------------------

@router.post("/{applicant_id}/contacts", response_model=ApiResponse)
def create_contact(
    applicant_id: int,
    data: ContactLogCreateRequest,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
):
    """新增一条联系记录，next_follow_at 用于生成待跟进任务"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    log = ContactLog(
        applicant_id=applicant_id,
        channel=data.channel,
        result=data.result,
        note=data.note,
        operator_id=staff.id,
        next_follow_at=data.next_follow_at,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    out = ContactLogOut.model_validate(log)
    out.operator_name = staff.real_name
    return ApiResponse(message="Contact logged.", data=out.model_dump(mode="json"))


@router.get("/{applicant_id}/contacts", response_model=ApiResponse)
def list_contacts(
    applicant_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """某候选人的联系历史（按时间倒序，附带操作人姓名）"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    rows = db.execute(
        select(ContactLog, Staff.real_name)
        .outerjoin(Staff, Staff.id == ContactLog.operator_id)
        .where(ContactLog.applicant_id == applicant_id)
        .order_by(ContactLog.created_at.desc(), ContactLog.id.desc())
    ).all()

    items = []
    for log, real_name in rows:
        out = ContactLogOut.model_validate(log)
        out.operator_name = real_name
        items.append(out.model_dump(mode="json"))
    return ApiResponse(data=items)


def _get_active_applicant(db: Session, applicant_id: int) -> Applicant:
    """读取未软删除的申请人，不存在则抛 404"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")
    return applicant


@router.post("/{applicant_id}/interviews", response_model=ApiResponse)
def create_interview(
    applicant_id: int,
    data: InterviewRecordCreateRequest,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
):
    """新增一条面试记录（1~3 轮）"""
    _get_active_applicant(db, applicant_id)

    record = InterviewRecord(
        applicant_id=applicant_id,
        round=data.round,
        interview_at=data.interview_at,
        result=data.result,
        comment=data.comment,
        operator_id=staff.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    out = InterviewRecordOut.model_validate(record)
    out.operator_name = staff.real_name
    return ApiResponse(message="Interview recorded.", data=out.model_dump(mode="json"))


@router.get("/{applicant_id}/interviews", response_model=ApiResponse)
def list_interviews(
    applicant_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """某候选人的面试记录（按轮次与时间倒序，附带操作人姓名）"""
    _get_active_applicant(db, applicant_id)

    rows = db.execute(
        select(InterviewRecord, Staff.real_name)
        .outerjoin(Staff, Staff.id == InterviewRecord.operator_id)
        .where(InterviewRecord.applicant_id == applicant_id)
        .order_by(
            InterviewRecord.round.desc(),
            InterviewRecord.created_at.desc(),
            InterviewRecord.id.desc(),
        )
    ).all()

    items = []
    for record, real_name in rows:
        out = InterviewRecordOut.model_validate(record)
        out.operator_name = real_name
        items.append(out.model_dump(mode="json"))
    return ApiResponse(data=items)


@router.get("/{applicant_id}", response_model=ApiResponse)
def get_applicant(
    applicant_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    data = ApplicantDetailOut.model_validate(applicant)
    data.resumes = [
        ResumeDocumentOut.model_validate(doc)
        for doc in db.scalars(
            select(ResumeDocument)
            .where(ResumeDocument.applicant_id == applicant_id)
            .order_by(ResumeDocument.created_at.desc(), ResumeDocument.id.desc())
        )
    ]
    data.sources = [
        CandidateSourceOut.model_validate(source)
        for source in db.scalars(
            select(CandidateSource)
            .where(CandidateSource.applicant_id == applicant_id)
            .order_by(CandidateSource.created_at.desc(), CandidateSource.id.desc())
        )
    ]
    return ApiResponse(data=data)


@router.get("/{applicant_id}/resume")
def download_resume(
    applicant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
):
    """简历附件下载：必须登录。

    简历存在公开静态目录之外，即使有人拿到 key 也无法通过 URL 直接访问，
    只能经这里校验 JWT 后读取；下载行为写入日志便于追溯。
    """
    # 单账号批量拉取的兜底限制；正常 HR 查看远低于该频率
    rate_limit(request, "resume_download", max_times=60, window=60)

    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    # 取最新一份简历（多简历表按创建时间倒序）
    doc = db.scalar(
        select(ResumeDocument)
        .where(ResumeDocument.applicant_id == applicant_id)
        .order_by(ResumeDocument.created_at.desc(), ResumeDocument.id.desc())
        .limit(1)
    )
    if not doc or not doc.oss_key.startswith("resume/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This applicant has no resume file.")

    path = _resolve_resume_path(doc.oss_key)
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file not found.")

    logger.info(
        "resume_download applicant_id=%s staff_id=%s username=%s ip=%s",
        applicant.id,
        staff.id,
        staff.username,
        request.client.host if request.client else "-",
    )

    filename = doc.file_name or os.path.basename(path)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{applicant_id}/media-url", response_model=ApiResponse)
def media_url(
    applicant_id: int,
    request: Request,
    key: str = Query(..., max_length=255),
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
):
    """为申请人媒体（照片/视频）签发短时效读取地址。

    照片/视频与简历同属个人数据，不再公开直读：
    - local/ 对象签发 10 分钟签名 URL，经 /api/media/{token} 读取
    - hr/ 对象（OSS）签发预签名 URL；未配置 OSS 时 404
    只允许签发该申请人名下 photo/video 两个 key，防止把接口当任意文件代理。
    """
    rate_limit(request, "media_url", max_times=120, window=60)

    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    if key not in (applicant.photo_oss_key, applicant.video_oss_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media key not found for this applicant.")

    if key.startswith("local/"):
        url = f"/api/media/{sign_media_token(key)}"
    elif key.startswith("hr/"):
        from app.utils.oss import generate_presigned_url

        try:
            url = generate_presigned_url(key)
        except ValueError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Media file not found.")
        except Exception:
            logger.exception("OSS presign failed for key=%s", key)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Media service is not available right now. Please try again later.",
            )
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media key not found for this applicant.")

    logger.info(
        "media_url applicant_id=%s staff_id=%s username=%s ip=%s",
        applicant.id,
        staff.id,
        staff.username,
        request.client.host if request.client else "-",
    )
    return ApiResponse(data={"url": url})


@router.patch("/{applicant_id}/status", response_model=ApiResponse)
def update_status(
    applicant_id: int,
    data: StatusUpdateRequest,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
):
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    from_status = applicant.status
    if from_status == data.to_status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This applicant is already in this status.")

    applicant.status = data.to_status
    if data.to_status == "hired":
        if data.salary is not None:
            applicant.salary = data.salary
        if data.employer is not None:
            applicant.employer = data.employer
        if data.hired_date is not None:
            applicant.hired_date = data.hired_date

    db.add(StatusHistory(
        applicant_id=applicant.id,
        from_status=from_status,
        to_status=data.to_status,
        operator_id=staff.id,
        note=data.note,
    ))
    db.commit()
    db.refresh(applicant)

    return ApiResponse(message="Status updated.", data=ApplicantOut.model_validate(applicant))


@router.get("/{applicant_id}/history", response_model=ApiResponse)
def get_status_history(
    applicant_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """状态流转时间轴（按时间倒序，附带操作人姓名）"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    rows = db.execute(
        select(StatusHistory, Staff.real_name)
        .outerjoin(Staff, Staff.id == StatusHistory.operator_id)
        .where(StatusHistory.applicant_id == applicant_id)
        .order_by(StatusHistory.created_at.desc(), StatusHistory.id.desc())
    ).all()

    items = [
        StatusHistoryItem(
            id=h.id,
            from_status=h.from_status,
            to_status=h.to_status,
            operator_id=h.operator_id,
            operator_name=real_name,
            note=h.note,
            created_at=h.created_at,
        )
        for h, real_name in rows
    ]
    return ApiResponse(data=[i.model_dump(mode="json") for i in items])


class ApplicantPatchRequest(ApplicantUpdateRequest):
    """后台编辑请求：补充一次性直传会话令牌，避免跨边界改动 schemas.py"""

    upload_session_token: str | None = Field(None, max_length=200)


@router.patch("/{applicant_id}", response_model=ApiResponse)
def update_applicant(
    applicant_id: int,
    data: ApplicantPatchRequest,
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """后台编辑申请人资料（只更新传入的字段，未传的保持原值）"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    updates = data.model_dump(exclude_unset=True)
    session_token = updates.pop("upload_session_token", None)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")

    # 简历单写 resume_document，不再通过通用 setattr 写入废弃主表列
    resume_key = updates.pop("resume_oss_key", None)
    resume_name = updates.pop("resume_file_name", None)

    changed_media = {
        field: updates[field]
        for field in ("photo_oss_key", "video_oss_key")
        if updates.get(field) and updates[field] != getattr(applicant, field)
    }
    if resume_key:
        changed_media["resume_oss_key"] = resume_key
    if changed_media:
        _validate_media_keys(changed_media, session_token)

    # 非空字段不允许显式传 null（否则会触发数据库 NOT NULL 报错）
    for required in ("first_name", "last_name", "phone", "availability"):
        if required in updates and updates[required] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{required} cannot be empty.")

    # 改手机号同样要柔性去重（排除自己与已软删除记录）
    if "phone" in updates:
        duplicate = db.scalar(
            select(Applicant.id).where(
                Applicant.phone == updates["phone"],
                Applicant.id != applicant_id,
                Applicant.deleted_at.is_(None),
            )
        )
        if duplicate:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Mobile number is already in use by another applicant.",
            )
        # 后台改号与提交接口共用同一套归一化，避免两处口径不一致
        updates["phone_normalized"] = normalize_ph_phone(updates["phone"])

    for field, value in updates.items():
        setattr(applicant, field, value)

    if resume_key:
        latest_doc = db.scalar(
            select(ResumeDocument)
            .where(ResumeDocument.applicant_id == applicant_id)
            .order_by(ResumeDocument.created_at.desc(), ResumeDocument.id.desc())
            .limit(1)
        )
        if not latest_doc or latest_doc.oss_key != resume_key:
            _add_resume_document(db, applicant.id, resume_key, resume_name)

    db.commit()
    db.refresh(applicant)

    return ApiResponse(message="Updated.", data=ApplicantOut.model_validate(applicant))


@router.delete("/{applicant_id}", response_model=ApiResponse)
def delete_applicant(
    applicant_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(require_admin),
):
    """软删除申请人（仅管理员；记录保留，列表与详情均不再返回）"""
    applicant = db.get(Applicant, applicant_id)
    if not applicant or applicant.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Applicant not found.")

    # 按业务时区打软删除时间戳，与 created_at 保持同一时间口径
    applicant.deleted_at = now_local()
    db.commit()

    return ApiResponse(message="Deleted.")
