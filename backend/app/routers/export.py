"""数据导出接口：申请人列表导出 Excel（xlsx）"""

import io
import logging
from datetime import date
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Applicant, Staff
from app.routers.applicant import apply_applicant_filters, require_admin
from app.utils.tz import now_local

router = APIRouter(prefix="/export", tags=["export"])
logger = logging.getLogger(__name__)

# 单次导出上限，保护服务器内存与 Excel 生成耗时
EXPORT_MAX_ROWS = 10000

# 以这些字符开头的文本会被 Excel 当成公式执行，导出前必须转义
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_cell(value):
    """防 Excel 公式注入：前置单引号，让 Excel 按纯文本处理

    lstrip() 同时去掉前导空格、制表符与换行：Excel 会忽略这些空白后
    再把 " =HYPERLINK(...)" 当成公式执行，只判断首字符会被绕过。
    """
    if isinstance(value, str) and value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def mask_phone(value: str | None) -> str | None:
    """手机号掩码：保留前 4 位与后 3 位（如 0917****567）。"""
    if not value:
        return value
    s = value.strip()
    if len(s) >= 7:
        return s[:4] + "*" * (len(s) - 7) + s[-3:]
    if len(s) >= 4:
        return s[:2] + "*" * (len(s) - 3) + s[-1:]
    return "*" * len(s)


def mask_email(value: str | None) -> str | None:
    """邮箱掩码：保留首字符与域名（如 j***@example.com）。"""
    if not value:
        return value
    s = value.strip()
    if "@" not in s:
        return "***"
    local, domain = s.split("@", 1)
    masked_local = "*" if len(local) <= 1 else local[0] + "***"
    return f"{masked_local}@{domain}"


def mask_id_number(value: str | None) -> str | None:
    """证件号掩码：保留前 2 位与后 2 位（如 P1****67）。"""
    if not value:
        return value
    s = value.strip()
    if len(s) > 4:
        return s[:2] + "*" * (len(s) - 4) + s[-2:]
    if len(s) > 2:
        return s[0] + "*" * (len(s) - 2) + s[-1]
    return "*" * len(s)


def mask_social(value: str | None) -> str | None:
    """社交账号掩码：保留首字符（保留 @ 前缀）。"""
    if not value:
        return value
    s = value.strip()
    if s.startswith("@") and len(s) > 2:
        return "@" + s[1] + "***"
    if len(s) > 1:
        return s[0] + "***"
    return "*"


def mask_url(value: str | None) -> str | None:
    """社交主页链接掩码：仅保留协议与主机名。"""
    if not value:
        return value
    s = value.strip()
    parsed = urlsplit(s)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/***"
    return "***"


def mask_birth_date(value: date | None) -> str:
    """出生日期掩码：仅保留年份（YYYY-**-**）。"""
    if not value:
        return ""
    return f"{value.year:04d}-**-**"


_EXPORT_HEADERS = [
    "ID", "Name", "Gender", "Birth Date", "Nationality", "Marital Status",
    "Mobile", "Alternate No.", "Email", "City", "Barangay", "Home Province",
    "FB Link", "FB Name", "TikTok",
    "ID 1 Type", "ID 1 Number", "NBI",
    "Target Job", "Expected Monthly Salary (PHP)", "Available Time", "Work Type", "Preferred Location", "Live-in",
    "Education", "English Level", "Chinese Level", "Last Job", "Work Experience",
    "Source", "Source Ref", "Referrer Phone",
    "Status", "Actual Salary (PHP)", "Employer", "Hired Date", "Internal Notes",
    "Created At",
]

_STATUS_MAP = {
    "new": "New", "contacted": "Contacted",
    "interview1": "Interview 1", "interview2": "Interview 2", "interview3": "Interview 3",
    "hired": "Hired", "lost": "Lost", "rejected": "Not suitable",
}

_SOURCE_MAP = {
    "self": "Self", "staff": "Staff", "referral": "Referral", "import": "Import",
}


def _build_applicant_row(a: Applicant, *, include_pii: bool) -> list:
    """构造单条申请人的 38 列导出数据（按需脱敏并统一防公式注入）。"""
    birth_date_val = (str(a.birth_date) if a.birth_date else "") if include_pii else mask_birth_date(a.birth_date)
    phone_val = a.phone if include_pii else mask_phone(a.phone)
    phone_alt_val = a.phone_alt if include_pii else mask_phone(a.phone_alt)
    email_val = a.email if include_pii else mask_email(a.email)
    fb_link_val = a.fb_profile_url if include_pii else mask_url(a.fb_profile_url)
    fb_name_val = a.fb_name if include_pii else mask_social(a.fb_name)
    tiktok_val = a.tiktok_username if include_pii else mask_social(a.tiktok_username)
    id1_num_val = a.id1_number if include_pii else mask_id_number(a.id1_number)
    referrer_phone_val = a.referrer_phone if include_pii else mask_phone(a.referrer_phone)

    values = [
        a.id,
        " ".join(part for part in (a.first_name, a.middle_name, a.last_name) if part),
        # gender 允许为空（AGENTS.md 硬约束），严禁填充默认值或 "Other"
        a.gender,
        birth_date_val,
        a.nationality,
        a.marital_status,
        phone_val,
        phone_alt_val,
        email_val,
        a.address_city,
        a.address_barangay,
        a.home_province,
        fb_link_val,
        fb_name_val,
        tiktok_val,
        a.id1_type,
        id1_num_val,
        "Yes" if a.has_nbi else "No",
        a.target_job,
        a.expected_salary,
        a.available_time,
        a.work_type,
        a.preferred_location,
        "Yes" if a.live_in_ok else "No",
        a.education,
        a.english_level,
        a.chinese_level,
        a.last_job,
        a.work_experience,
        _SOURCE_MAP.get(a.source_type, a.source_type),
        a.source_ref,
        referrer_phone_val,
        _STATUS_MAP.get(a.status, a.status),
        a.salary,
        a.employer,
        str(a.hired_date) if a.hired_date else "",
        a.internal_remark,
        str(a.created_at),
    ]
    return [safe_cell(v) for v in values]


@router.get("/applicant")
def export_applicants(
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(new|contacted|interview1|interview2|interview3|hired|lost|rejected)$",
    ),
    source_type: str | None = Query(
        None, pattern="^(self|staff|referral|import)$"
    ),
    availability: int | None = Query(None, ge=0, le=3),
    intent_tag: str | None = Query(None, pattern="^[a-z0-9-]{1,32}$"),
    keyword: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    gender: str | None = Query(None, pattern="^(male|female|unspecified)$"),
    age_min: int | None = Query(None, ge=0, le=120),
    age_max: int | None = Query(None, ge=0, le=120),
    include_pii: bool = Query(
        False,
        description="Whether to export unmasked PII (admin only). Defaults to masked.",
    ),
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(require_admin),
):
    """导出申请人列表为 Excel（仅管理员；默认 PII 掩码脱敏，传 include_pii=true 导出明文）"""
    if include_pii and current_staff.role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not have permission to export unmasked PII.",
        )

    stmt = select(Applicant).where(Applicant.deleted_at.is_(None))
    # 与列表页共用同一套筛选条件，保证「筛出来的」和「导出的」一致
    stmt = apply_applicant_filters(
        stmt,
        status_filter=status_filter,
        source_type=source_type,
        availability=availability,
        intent_tag=intent_tag,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        gender=gender,
        age_min=age_min,
        age_max=age_max,
    )

    # 上限保护：多取 1 行用于精确判断是否发生截断，禁止静默截断
    stmt = stmt.order_by(Applicant.created_at.desc(), Applicant.id.desc()).limit(EXPORT_MAX_ROWS + 1)
    rows_fetched = list(db.scalars(stmt).all())
    truncated = len(rows_fetched) > EXPORT_MAX_ROWS
    applicants = rows_fetched[:EXPORT_MAX_ROWS]

    # 创建流式只写工作簿，降低万行导出时的内存与 XML 序列化开销
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="Applicants")

    # 采样前 100 行预计算列宽；write_only 模式必须在首次 ws.append 前写入 column_dimensions
    sampled_rows = [_build_applicant_row(a, include_pii=include_pii) for a in applicants[:100]]
    col_lengths = [len(header) for header in _EXPORT_HEADERS]
    for row in sampled_rows:
        for idx, val in enumerate(row):
            if val:
                col_lengths[idx] = max(col_lengths[idx], len(str(val)))
    for col_idx, max_len in enumerate(col_lengths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

    # 表头行
    header_fill = PatternFill(start_color="409EFF", end_color="409EFF", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    header_cells = []
    for header in _EXPORT_HEADERS:
        cell = WriteOnlyCell(ws, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        header_cells.append(cell)
    ws.append(header_cells)

    # 数据行：先输出已采样的前 100 行，再流式追加剩余行
    for row in sampled_rows:
        ws.append(row)
    for a in applicants[100:]:
        ws.append(_build_applicant_row(a, include_pii=include_pii))

    if truncated:
        notice_text = (
            f"NOTICE: Export truncated at {EXPORT_MAX_ROWS} rows. "
            "Narrow your filters to export the remaining records."
        )
        notice_fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
        notice_font = Font(color="B45309", bold=True)
        notice_cells = []
        for col_idx in range(1, len(_EXPORT_HEADERS) + 1):
            cell = WriteOnlyCell(ws, value=safe_cell(notice_text) if col_idx == 1 else None)
            cell.fill = notice_fill
            cell.font = notice_font
            notice_cells.append(cell)
        ws.append(notice_cells)

    # 写入内存
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # 审计日志：不记录 keyword/手机号/证件号等明文 PII
    logger.info(
        "applicant_export staff_id=%s username=%s role=%s include_pii=%s row_count=%s truncated=%s filters=%s",
        current_staff.id,
        current_staff.username,
        current_staff.role,
        include_pii,
        len(applicants),
        truncated,
        {
            "status": status_filter,
            "source_type": source_type,
            "availability": availability,
            "intent_tag": intent_tag,
            "has_keyword": bool(keyword and keyword.strip()),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "gender": gender,
            "age_min": age_min,
            "age_max": age_max,
        },
    )

    # 生成文件名
    timestamp = now_local().strftime("%Y%m%d_%H%M%S")
    filename = f"applicants_{timestamp}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Export-Truncated": "true" if truncated else "false",
            "X-Export-Max-Rows": str(EXPORT_MAX_ROWS),
            "Access-Control-Expose-Headers": "X-Export-Truncated, X-Export-Max-Rows",
        },
    )
