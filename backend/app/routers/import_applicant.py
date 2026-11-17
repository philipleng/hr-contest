"""批量导入 API：模板下载、Excel 上传导入、导入批次历史"""

import io
import json
import math
import os
import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Applicant, CandidateSource, ImportBatch, Staff, StatusHistory
from app.schemas import ApiResponse
from app.utils.auth_deps import get_current_staff
from app.utils.phone import normalize_ph_phone

router = APIRouter(prefix="/import", tags=["import"])

MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ROWS = 2000
MAX_INTENT_TAGS = 10
MAX_MYSQL_INT = 2_147_483_647
MAX_FAIL_DETAIL_BYTES = 65000

_TAG_PATTERN = re.compile(r"^[a-z0-9-]{1,32}$")
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_POSITIVE_INT_PATTERN = re.compile(r"^\d+$")

_VALID_GENDERS = frozenset({"male", "female"})
_VALID_LEVELS = frozenset({"none", "basic", "fluent"})
_VALID_AVAILABILITY = frozenset({0, 1, 2, 3})

TEMPLATE_HEADERS: list[str] = [
    "First Name*",
    "Middle Name",
    "Last Name*",
    "Mobile*",
    "Alternate Mobile",
    "Gender",
    "Birth Date",
    "Email",
    "City",
    "Barangay",
    "Target Job",
    "Expected Salary",
    "Availability",
    "Intent Tags",
    "Education",
    "English Level",
    "Chinese Level",
    "Work Experience",
    "Notes",
]

_HEADER_TO_FIELD: dict[str, str] = {
    "first name": "first_name",
    "middle name": "middle_name",
    "last name": "last_name",
    "mobile": "mobile",
    "alternate mobile": "alternate_mobile",
    "gender": "gender",
    "birth date": "birth_date",
    "email": "email",
    "city": "city",
    "barangay": "barangay",
    "target job": "target_job",
    "expected salary": "expected_salary",
    "availability": "availability",
    "intent tags": "intent_tags",
    "education": "education",
    "english level": "english_level",
    "chinese level": "chinese_level",
    "work experience": "work_experience",
    "notes": "notes",
}

_REQUIRED_FIELDS = ("first_name", "last_name", "mobile")

_FIELD_DISPLAY_NAMES: dict[str, str] = {
    "first_name": "First Name",
    "last_name": "Last Name",
    "mobile": "Mobile",
}

_HEADER_COMMENTS: dict[str, str] = {
    "Gender": "Optional: male, female, or leave blank",
    "Birth Date": "Format: YYYY-MM-DD",
    "Availability": "0=Unknown, 1=Looking, 2=Employed, 3=Not looking",
    "Intent Tags": "Comma-separated tags (lowercase letters, digits, hyphens), max 10",
    "English Level": "Optional: none, basic, or fluent",
    "Chinese Level": "Optional: none, basic, or fluent",
}

_TEMPLATE_SAMPLE_ROW: list[Any] = [
    "Maria",
    "Santos",
    "Reyes",
    "09171234567",
    "09181234567",
    "female",
    "1998-05-20",
    "maria.reyes@example.com",
    "Makati",
    "Bel-Air",
    "Customer Service",
    25000,
    1,
    "bpo,customer-service",
    "College Graduate",
    "fluent",
    "none",
    "2 years BPO voice support",
    "Walk-in applicant (Gender: male, female, or leave blank)",
]


class ImportFailureItem(BaseModel):
    row: int
    reason: str


class ImportResultData(BaseModel):
    batch_id: int
    file_name: str
    total_count: int
    success_count: int
    fail_count: int
    failures: list[ImportFailureItem]
    created_at: str


class ImportBatchOut(BaseModel):
    id: int
    file_name: str
    total_count: int
    success_count: int
    fail_count: int
    failures: list[ImportFailureItem]
    operator_id: int | None = None
    operator_name: str | None = None
    created_at: str


class ImportBatchListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ImportBatchOut]


def _normalize_header(val: Any) -> str:
    if val is None:
        return ""
    cleaned = str(val).strip().rstrip("*").strip().lower()
    return " ".join(cleaned.split())


def _is_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _cell_to_clean_str(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if not math.isfinite(val):
            return None
        if val.is_integer():
            return str(int(val))
        return str(val)
    s = str(val).strip()
    return s if s else None


def _parse_phone_cell(val: Any) -> tuple[str | None, bool]:
    """解析手机号单元格；对非整数浮点数直接判错，整数/整数浮点先转为整数字符串。"""
    if _is_blank(val):
        return None, True
    if isinstance(val, bool):
        return None, False
    if isinstance(val, float):
        if not math.isfinite(val) or not val.is_integer():
            return None, False
        raw = str(int(val))
    elif isinstance(val, int):
        raw = str(val)
    else:
        raw = str(val).strip()
    norm = normalize_ph_phone(raw)
    if not norm:
        return None, False
    return norm, True


def _parse_birth_date_cell(val: Any) -> tuple[date | None, bool]:
    if _is_blank(val):
        return None, True
    if isinstance(val, datetime):
        return val.date(), True
    if isinstance(val, date):
        return val, True
    if isinstance(val, str):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d").date(), True
        except ValueError:
            return None, False
    return None, False


def _parse_non_negative_int(val: Any) -> int | None:
    """解析非负整数（用于 Expected Salary）；不合法返回 None。"""
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if 0 <= val <= MAX_MYSQL_INT else None
    if isinstance(val, float):
        if not math.isfinite(val) or not val.is_integer():
            return None
        parsed = int(val)
        return parsed if 0 <= parsed <= MAX_MYSQL_INT else None
    if isinstance(val, str):
        s = val.strip()
        if not _POSITIVE_INT_PATTERN.fullmatch(s):
            return None
        parsed = int(s)
        return parsed if 0 <= parsed <= MAX_MYSQL_INT else None
    return None


def _parse_availability_cell(val: Any) -> tuple[int, bool]:
    if _is_blank(val):
        return 0, True
    parsed = _parse_non_negative_int(val)
    if parsed is None or parsed not in _VALID_AVAILABILITY:
        return 0, False
    return parsed, True


def _parse_level_cell(val: Any) -> tuple[str | None, bool]:
    s = _cell_to_clean_str(val)
    if s is None:
        return None, True
    lowered = s.lower()
    if lowered not in _VALID_LEVELS:
        return None, False
    return lowered, True


def _parse_intent_tags_cell(val: Any) -> tuple[str | None, str | None]:
    s = _cell_to_clean_str(val)
    if s is None:
        return None, None
    tags = [part.strip().lower() for part in s.split(",") if part.strip()]
    tags = list(dict.fromkeys(tags))
    if not tags:
        return None, None
    if len(tags) > MAX_INTENT_TAGS:
        return None, f"At most {MAX_INTENT_TAGS} intent tags are allowed"
    for tag in tags:
        if not _TAG_PATTERN.fullmatch(tag):
            return None, f"Invalid intent tag '{tag}' (must match ^[a-z0-9-]{{1,32}}$)"
    joined = ",".join(tags)
    if len(joined) > 255:
        return None, "Intent tags exceed maximum length of 255 characters"
    return joined, None


def _truncate_text(val: Any, max_length: int) -> str | None:
    s = _cell_to_clean_str(val)
    if s is None:
        return None
    return s[:max_length]


def _serialize_failures_for_db(failures: list[dict[str, Any]]) -> str:
    """序列化失败明细，并确保不超过 MySQL 5.7 TEXT 列的 64KB 上限。"""
    encoded = json.dumps(failures, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= MAX_FAIL_DETAIL_BYTES:
        return encoded

    kept: list[dict[str, Any]] = []
    for item in failures:
        candidate = kept + [
            item,
            {"row": 0, "reason": f"... truncated ({len(failures) - len(kept) - 1} more errors)"},
        ]
        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > MAX_FAIL_DETAIL_BYTES:
            break
        kept.append(item)
    kept.append({"row": 0, "reason": f"... truncated ({len(failures) - len(kept)} more errors)"})
    return json.dumps(kept, ensure_ascii=False)


def _parse_fail_detail(raw: str | None) -> list[ImportFailureItem]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    items: list[ImportFailureItem] = []
    for entry in parsed:
        if isinstance(entry, dict) and "row" in entry and "reason" in entry:
            try:
                items.append(ImportFailureItem(row=int(entry["row"]), reason=str(entry["reason"])))
            except (TypeError, ValueError):
                continue
    return items


@router.get("/template")
def download_import_template(_: Staff = Depends(get_current_staff)):
    """下载申请人批量导入 Excel 模板（.xlsx）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Applicants"

    header_fill = PatternFill(start_color="409EFF", end_color="409EFF", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_alignment = Alignment(horizontal="center", vertical="center")

    for col_idx, header in enumerate(TEMPLATE_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        if header in _HEADER_COMMENTS:
            cell.comment = Comment(_HEADER_COMMENTS[header], "HR System")

    ws.row_dimensions[1].height = 24

    for col_idx, sample_val in enumerate(_TEMPLATE_SAMPLE_ROW, 1):
        cell = ws.cell(row=2, column=col_idx, value=sample_val)
        if TEMPLATE_HEADERS[col_idx - 1] in ("Mobile*", "Alternate Mobile", "Birth Date"):
            cell.number_format = "@"

    for col in ws.iter_cols(min_row=1, max_row=2):
        max_len = max((len(str(c.value)) for c in col if c.value is not None), default=12)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 4, 16), 38)

    guide = wb.create_sheet(title="Instructions")
    guide.append(["Column", "Required", "Accepted Values / Notes"])
    for cell in guide[1]:
        cell.font = Font(bold=True)
    guide.append(["First Name*, Last Name*", "Yes", "Applicant first and last name"])
    guide.append(["Mobile*", "Yes", "Philippine mobile number, e.g. 09171234567 or +639171234567"])
    guide.append(["Alternate Mobile", "No", "Optional backup Philippine mobile number"])
    guide.append(["Gender", "No", "Allowed: male, female, or leave blank (do not enter Other)"])
    guide.append(["Birth Date", "No", "Format: YYYY-MM-DD"])
    guide.append(["Expected Salary", "No", "Non-negative integer (PHP)"])
    guide.append(["Availability", "No", "0=Unknown (default), 1=Looking, 2=Employed, 3=Not looking"])
    guide.append(["Intent Tags", "No", "Comma-separated lowercase tags (a-z, 0-9, -), max 10"])
    guide.append(["English Level / Chinese Level", "No", "Allowed: none, basic, fluent, or leave blank"])
    guide.column_dimensions["A"].width = 30
    guide.column_dimensions["B"].width = 12
    guide.column_dimensions["C"].width = 64

    wb.active = 0

    buffer = io.BytesIO()
    wb.save(buffer)
    wb.close()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=applicant_import_template.xlsx",
        },
    )


@router.post("/applicant", response_model=ApiResponse)
def import_applicants(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff),
):
    """批量导入申请人（.xlsx，单次最多 2,000 行，单文件 ≤ 10MB）。"""
    raw_name = (file.filename or "").strip()
    if not raw_name.lower().endswith(".xlsx"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only .xlsx files are supported.",
        )
    safe_filename = (os.path.basename(raw_name) or "import.xlsx")[:255]

    content = file.file.read(MAX_IMPORT_FILE_BYTES + 1)
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "File size exceeds the 10MB limit.",
        )

    wb = None
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Workbook has no active worksheet.")

        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row or all(_is_blank(cell) for cell in header_row):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing header row in worksheet.")

        col_map: dict[str, int] = {}
        for idx, cell in enumerate(header_row):
            field_key = _HEADER_TO_FIELD.get(_normalize_header(cell))
            if field_key and field_key not in col_map:
                col_map[field_key] = idx

        missing_required = [
            _FIELD_DISPLAY_NAMES[f] for f in _REQUIRED_FIELDS if f not in col_map
        ]
        if missing_required:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Missing required column(s): {', '.join(missing_required)}.",
            )

        data_rows: list[tuple[int, tuple[Any, ...]]] = []
        for row_num, row_values in enumerate(rows_iter, start=2):
            if not row_values or all(_is_blank(cell) for cell in row_values):
                continue
            data_rows.append((row_num, row_values))
            if len(data_rows) > MAX_IMPORT_ROWS:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Too many rows: maximum {MAX_IMPORT_ROWS} data rows allowed per import.",
                )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid or corrupted .xlsx file.",
        )
    finally:
        if wb is not None:
            wb.close()

    # 预先加载库内活跃（未软删除）申请人手机号，做柔性去重
    active_phone_rows = db.execute(
        select(Applicant.phone, Applicant.phone_normalized).where(
            Applicant.deleted_at.is_(None)
        )
    ).all()
    existing_phones: set[str] = set()
    for phone, phone_norm in active_phone_rows:
        if phone:
            existing_phones.add(normalize_ph_phone(phone) or phone)
        if phone_norm:
            existing_phones.add(normalize_ph_phone(phone_norm) or phone_norm)

    seen_phones: set[str] = set()
    failures: list[dict[str, Any]] = []
    applicants_to_insert: list[Applicant] = []

    def _get(row_vals: tuple[Any, ...], field: str) -> Any:
        idx = col_map.get(field)
        if idx is None or idx >= len(row_vals):
            return None
        return row_vals[idx]

    for row_num, row_vals in data_rows:
        errors: list[str] = []

        first_name = _truncate_text(_get(row_vals, "first_name"), 64)
        if not first_name:
            errors.append("First Name is required")

        middle_name = _truncate_text(_get(row_vals, "middle_name"), 64)

        last_name = _truncate_text(_get(row_vals, "last_name"), 64)
        if not last_name:
            errors.append("Last Name is required")

        raw_mobile = _get(row_vals, "mobile")
        norm_phone: str | None = None
        if _is_blank(raw_mobile):
            errors.append("Mobile is required")
        else:
            norm_phone, phone_ok = _parse_phone_cell(raw_mobile)
            if not phone_ok or not norm_phone:
                errors.append("Invalid Mobile number (expected Philippine 09XXXXXXXXX)")
            elif norm_phone in existing_phones:
                errors.append(f"Mobile {norm_phone} already exists in active applicants")
            elif norm_phone in seen_phones:
                errors.append(f"Duplicate Mobile {norm_phone} in file")

        raw_alt_mobile = _get(row_vals, "alternate_mobile")
        norm_alt_phone, alt_ok = _parse_phone_cell(raw_alt_mobile)
        if not alt_ok:
            errors.append("Invalid Alternate Mobile number")

        gender_raw = _cell_to_clean_str(_get(row_vals, "gender"))
        gender: str | None = None
        if gender_raw is not None:
            gender_lower = gender_raw.lower()
            if gender_lower not in _VALID_GENDERS:
                errors.append("Gender must be 'male', 'female', or blank")
            else:
                gender = gender_lower

        birth_date, bd_ok = _parse_birth_date_cell(_get(row_vals, "birth_date"))
        if not bd_ok:
            errors.append("Invalid Birth Date (expected YYYY-MM-DD)")

        email_raw = _cell_to_clean_str(_get(row_vals, "email"))
        email: str | None = None
        if email_raw is not None:
            if len(email_raw) > 128 or not _EMAIL_PATTERN.fullmatch(email_raw):
                errors.append("Invalid Email format")
            else:
                email = email_raw

        city = _truncate_text(_get(row_vals, "city"), 64)
        barangay = _truncate_text(_get(row_vals, "barangay"), 64)
        target_job = _truncate_text(_get(row_vals, "target_job"), 128)

        raw_salary = _get(row_vals, "expected_salary")
        expected_salary: int | None = None
        if not _is_blank(raw_salary):
            expected_salary = _parse_non_negative_int(raw_salary)
            if expected_salary is None:
                errors.append("Expected Salary must be a non-negative integer")

        availability, avail_ok = _parse_availability_cell(_get(row_vals, "availability"))
        if not avail_ok:
            errors.append("Availability must be 0, 1, 2, or 3")

        intent_tags, tags_err = _parse_intent_tags_cell(_get(row_vals, "intent_tags"))
        if tags_err:
            errors.append(tags_err)

        education = _truncate_text(_get(row_vals, "education"), 64)

        english_level, eng_ok = _parse_level_cell(_get(row_vals, "english_level"))
        if not eng_ok:
            errors.append("English Level must be 'none', 'basic', or 'fluent'")

        chinese_level, chi_ok = _parse_level_cell(_get(row_vals, "chinese_level"))
        if not chi_ok:
            errors.append("Chinese Level must be 'none', 'basic', or 'fluent'")

        work_experience = _truncate_text(_get(row_vals, "work_experience"), 16000)
        notes = _truncate_text(_get(row_vals, "notes"), 16000)

        if errors:
            failures.append({"row": row_num, "reason": "; ".join(errors)})
            continue

        assert norm_phone is not None
        assert first_name is not None
        assert last_name is not None

        seen_phones.add(norm_phone)
        applicants_to_insert.append(
            Applicant(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                gender=gender,
                birth_date=birth_date,
                phone=norm_phone,
                phone_alt=norm_alt_phone,
                phone_normalized=norm_phone,
                email=email,
                address_city=city,
                address_barangay=barangay,
                target_job=target_job,
                expected_salary=expected_salary,
                availability=availability,
                intent_tags=intent_tags,
                education=education,
                english_level=english_level,
                chinese_level=chinese_level,
                work_experience=work_experience,
                applicant_remark=notes,
                source_type="import",
                source_ref=current_staff.username,
                status="new",
                created_by=current_staff.id,
            )
        )

    total_count = len(data_rows)
    success_count = len(applicants_to_insert)
    fail_count = len(failures)

    if applicants_to_insert:
        db.add_all(applicants_to_insert)
        db.flush()
        for applicant in applicants_to_insert:
            db.add(
                StatusHistory(
                    applicant_id=applicant.id,
                    from_status=None,
                    to_status="new",
                    operator_id=current_staff.id,
                    note="Bulk import",
                )
            )
            db.add(
                CandidateSource(
                    applicant_id=applicant.id,
                    platform="import",
                )
            )

    batch = ImportBatch(
        file_name=safe_filename,
        total_count=total_count,
        success_count=success_count,
        fail_count=fail_count,
        fail_detail=_serialize_failures_for_db(failures),
        operator_id=current_staff.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    result = ImportResultData(
        batch_id=batch.id,
        file_name=batch.file_name,
        total_count=total_count,
        success_count=success_count,
        fail_count=fail_count,
        failures=[ImportFailureItem(**f) for f in failures],
        created_at=batch.created_at.isoformat(),
    )
    return ApiResponse(
        message="Import completed.",
        data=result.model_dump(mode="json"),
    )


@router.get("/batches", response_model=ApiResponse)
def list_import_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """分页查询批量导入历史记录（按时间与 ID 倒序）。"""
    total = db.scalar(select(func.count(ImportBatch.id))) or 0

    rows = db.execute(
        select(ImportBatch, Staff.real_name)
        .outerjoin(Staff, Staff.id == ImportBatch.operator_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        ImportBatchOut(
            id=batch.id,
            file_name=batch.file_name,
            total_count=batch.total_count,
            success_count=batch.success_count,
            fail_count=batch.fail_count,
            failures=_parse_fail_detail(batch.fail_detail),
            operator_id=batch.operator_id,
            operator_name=operator_name,
            created_at=batch.created_at.isoformat(),
        )
        for batch, operator_name in rows
    ]

    data = ImportBatchListData(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )
    return ApiResponse(data=data.model_dump(mode="json"))
