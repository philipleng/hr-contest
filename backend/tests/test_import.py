"""IMP 组 P0 用例：批量导入模板下载、Excel 上传导入、柔性去重、导入批次分页与鉴权"""

import io
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.models import Applicant, CandidateSource, ImportBatch, StatusHistory
from app.routers import import_applicant as import_router
from app.routers.import_applicant import TEMPLATE_HEADERS
from app.utils.tz import now_local

TEMPLATE_URL = "/api/import/template"
IMPORT_URL = "/api/import/applicant"
BATCHES_URL = "/api/import/batches"


def _build_xlsx(rows: list[list[object]], *, headers: list[str] | None = None) -> bytes:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="Applicants")
    if headers is not None:
        ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def _upload_xlsx(client, headers, content: bytes, filename: str = "applicants.xlsx"):
    return client.post(
        IMPORT_URL,
        headers=headers,
        files={
            "file": (
                filename,
                io.BytesIO(content),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_import_requires_auth(client):
    """未登录访问导入相关接口一律返回 401。"""
    assert client.get(TEMPLATE_URL).status_code == 401
    assert client.get(BATCHES_URL).status_code == 401
    xlsx = _build_xlsx([], headers=TEMPLATE_HEADERS)
    assert _upload_xlsx(client, {}, xlsx).status_code == 401


def test_download_template_and_reimport_sample(client, db_session, staff_headers):
    """GET /api/import/template 返回标准 19 列表头与合法示例行，且可直接导入。"""
    resp = client.get(TEMPLATE_URL, headers=staff_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "applicant_import_template.xlsx" in resp.headers["content-disposition"]

    wb = load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    assert len(rows) == 2
    assert len(rows[0]) == 19
    assert list(rows[0]) == TEMPLATE_HEADERS
    assert rows[1][3] == "09171234567"
    assert rows[1][5] == "female"

    # 下载后的模板应可直接被上传接口解析并成功导入示例行
    import_resp = _upload_xlsx(client, staff_headers, resp.content, "template_sample.xlsx")
    assert import_resp.status_code == 200, import_resp.text
    data = import_resp.json()["data"]
    assert data["total_count"] == 1
    assert data["success_count"] == 1
    assert data["fail_count"] == 0
    assert data["failures"] == []

    saved = db_session.scalar(select(Applicant).where(Applicant.phone == "09171234567"))
    assert saved is not None
    assert saved.source_type == "import"
    assert saved.status == "new"


def test_import_valid_rows_numeric_phone_and_nullable_gender(
    client, db_session, make_staff, make_auth_headers
):
    """支持整数/浮点手机号、空白行跳过、大小写/星号表头匹配、gender 留空存 None。"""
    staff = make_staff("importer_1", role="staff", real_name="Importer One")
    headers = make_auth_headers(staff)

    custom_headers = [
        " first name * ",
        "middle name",
        "LAST NAME*",
        "mobile",
        "alternate mobile ",
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
    rows = [
        [
            "Juan",
            "M",
            "Cruz",
            9171112233,  # int phone
            9182223344.0,  # float phone
            None,  # gender blank -> None
            date(1995, 3, 15),
            "juan@example.com",
            "Makati",
            "Poblacion",
            "Driver",
            28000.0,
            1,
            " Driver, BPO, driver ",
            "High School",
            "Fluent",
            "BASIC",
            "3 yrs delivery",
            "Good attitude",
        ],
        [None] * 19,  # completely blank row, should be skipped
        [
            "Ana",
            "",
            "Santos",
            9174445566.0,  # float phone
            "",
            "MALE",
            "1999-11-02",
            "",
            "Pasay",
            "",
            "Cashier",
            "20000",
            "",  # availability blank -> 0
            "",
            "College",
            "",
            "NONE",
            "",
            "",
        ],
    ]

    xlsx = _build_xlsx(rows, headers=custom_headers)
    resp = _upload_xlsx(client, headers, xlsx, "BATCH_OK.XLSX")
    assert resp.status_code == 200, resp.text
    payload = resp.json()["data"]

    assert payload["file_name"] == "BATCH_OK.XLSX"
    assert payload["total_count"] == 2
    assert payload["success_count"] == 2
    assert payload["fail_count"] == 0
    assert payload["failures"] == []
    assert payload["batch_id"] > 0
    assert payload["created_at"]

    juan = db_session.scalar(select(Applicant).where(Applicant.phone == "09171112233"))
    ana = db_session.scalar(select(Applicant).where(Applicant.phone == "09174445566"))
    assert juan is not None and ana is not None

    assert juan.phone_normalized == "09171112233"
    assert juan.phone_alt == "09182223344"
    assert juan.gender is None
    assert juan.birth_date == date(1995, 3, 15)
    assert juan.expected_salary == 28000
    assert juan.availability == 1
    assert juan.intent_tags == "driver,bpo"
    assert juan.english_level == "fluent"
    assert juan.chinese_level == "basic"
    assert juan.applicant_remark == "Good attitude"
    assert juan.source_type == "import"
    assert juan.source_ref == "importer_1"
    assert juan.status == "new"
    assert juan.created_by == staff.id

    assert ana.gender == "male"
    assert ana.birth_date == date(1999, 11, 2)
    assert ana.expected_salary == 20000
    assert ana.availability == 0
    assert ana.chinese_level == "none"
    assert ana.source_type == "import"
    assert ana.created_by == staff.id

    assert db_session.scalar(select(func.count(StatusHistory.id))) == 2
    assert db_session.scalar(select(func.count(CandidateSource.id))) == 2


def test_import_mixed_batch_rejects_other_gender_and_bad_rows(
    client, db_session, staff_headers
):
    """混合批次：gender=other/非法手机号/非法日期等计入 failures，合法行正常入库。"""
    rows = [
        # row 2: valid
        ["Valid", None, "One", "09170000001", None, "female", "1996-01-10"],
        # row 3: gender="other" (strictly forbidden)
        ["Bad", None, "Gender", "09170000002", None, "other", "1996-01-10"],
        # row 4: invalid mobile + invalid alternate mobile + invalid birth date + invalid email
        ["Bad", None, "Mobile", "12345", "999", "male", "10/01/1996", "not-an-email"],
        # row 5: non-integer float phone
        ["Bad", None, "FloatPhone", 917000000.5, None, None, None],
        # row 6: missing required first_name & last_name
        ["", None, "", "09170000003", None, None, None],
        # row 7: invalid salary / availability / english_level / too many tags
        [
            "Bad",
            None,
            "Fields",
            "09170000004",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            -100,
            9,
            "t1,t2,t3,t4,t5,t6,t7,t8,t9,t10,t11",
            None,
            "native",
            "bad_level",
        ],
        # row 8: valid with datetime object birth_date
        ["Valid", None, "Two", "+639170000005", None, "", datetime(1994, 7, 20, 0, 0)],
    ]
    xlsx = _build_xlsx(rows, headers=TEMPLATE_HEADERS)
    resp = _upload_xlsx(client, staff_headers, xlsx, "mixed.xlsx")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["total_count"] == 7
    assert data["success_count"] == 2
    assert data["fail_count"] == 5

    fail_by_row = {f["row"]: f["reason"] for f in data["failures"]}
    assert set(fail_by_row) == {3, 4, 5, 6, 7}
    assert "Gender" in fail_by_row[3]
    assert "Mobile" in fail_by_row[4]
    assert "Alternate Mobile" in fail_by_row[4]
    assert "Birth Date" in fail_by_row[4]
    assert "Email" in fail_by_row[4]
    assert "Mobile" in fail_by_row[5]
    assert "First Name" in fail_by_row[6]
    assert "Last Name" in fail_by_row[6]
    assert "Expected Salary" in fail_by_row[7]
    assert "Availability" in fail_by_row[7]
    assert "10 intent tags" in fail_by_row[7]
    assert "English Level" in fail_by_row[7]
    assert "Chinese Level" in fail_by_row[7]

    phones = set(db_session.scalars(select(Applicant.phone)).all())
    assert phones == {"09170000001", "09170000005"}


def test_import_dedup_active_in_batch_and_allows_soft_deleted(
    client, db_session, staff_headers, submit_payload
):
    """活跃记录与批次内重复手机号跳过；前序失败行不占用去重名额；已软删除记录允许重新导入。"""
    # 1) Active applicant in DB
    res_active = client.post(
        "/api/applicant/submit",
        json=submit_payload(phone="09178880001", first_name="Active", last_name="User"),
    )
    assert res_active.status_code == 200

    # 2) Soft-deleted applicant in DB
    res_deleted = client.post(
        "/api/applicant/submit",
        json=submit_payload(phone="09178880002", first_name="Deleted", last_name="User"),
    )
    assert res_deleted.status_code == 200
    deleted_id = res_deleted.json()["data"]["applicant_id"]
    db_session.get(Applicant, deleted_id).deleted_at = now_local()
    db_session.commit()

    rows = [
        # row 2: duplicates active DB record
        ["Dup", None, "DB", "+639178880001", None, "male"],
        # row 3: re-import soft-deleted phone -> MUST succeed
        ["Reimport", None, "SoftDel", "09178880002", None, "female"],
        # row 4: fails on gender -> should NOT reserve 09178880003 in seen_phones
        ["Fail", None, "First", "09178880003", None, "other"],
        # row 5: same phone 09178880003 now valid -> MUST succeed
        ["Win", None, "Second", 9178880003, None, "male"],
        # row 6: duplicates row 5 within same batch -> MUST fail
        ["Dup", None, "Batch", "0917-888-0003", None, "male"],
    ]
    xlsx = _build_xlsx(rows, headers=TEMPLATE_HEADERS)
    resp = _upload_xlsx(client, staff_headers, xlsx, "dedup.xlsx")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["total_count"] == 5
    assert data["success_count"] == 2
    assert data["fail_count"] == 3
    fail_rows = {f["row"]: f["reason"] for f in data["failures"]}
    assert set(fail_rows) == {2, 4, 6}
    assert "already exists" in fail_rows[2]
    assert "Gender" in fail_rows[4]
    assert "Duplicate Mobile" in fail_rows[6]

    active_rows = list(
        db_session.scalars(
            select(Applicant).where(Applicant.deleted_at.is_(None))
        ).all()
    )
    assert {a.phone for a in active_rows} == {"09178880001", "09178880002", "09178880003"}


def test_import_file_level_rejections(client, db_session, staff_headers, monkeypatch):
    """拦截非 .xlsx、损坏文件、缺必填表头、超 10MB、超 2,000 行。"""
    # 1. Non-.xlsx extension
    resp_csv = _upload_xlsx(client, staff_headers, b"a,b,c\n1,2,3\n", "data.csv")
    assert resp_csv.status_code == 400

    # 2. Corrupted .xlsx
    resp_bad = _upload_xlsx(client, staff_headers, b"not-a-zip-xlsx", "corrupt.xlsx")
    assert resp_bad.status_code == 400

    # 3. Missing required header (Mobile omitted)
    missing_header_xlsx = _build_xlsx(
        [["Juan", "Cruz"]],
        headers=["First Name*", "Last Name*"],
    )
    resp_hdr = _upload_xlsx(client, staff_headers, missing_header_xlsx, "no_mobile.xlsx")
    assert resp_hdr.status_code == 400

    # 4. File size > limit
    monkeypatch.setattr(import_router, "MAX_IMPORT_FILE_BYTES", 100)
    big_xlsx = _build_xlsx([["Juan", None, "Cruz", "09171234567"]], headers=TEMPLATE_HEADERS)
    assert len(big_xlsx) > 100
    resp_big = _upload_xlsx(client, staff_headers, big_xlsx, "too_big.xlsx")
    assert resp_big.status_code in (400, 413)
    monkeypatch.undo()

    # 5. Exceeding 2,000 data rows -> 400 and 0 rows inserted
    too_many_rows = [
        [f"User{i}", None, "Test", f"0917{i:07d}"] for i in range(2001)
    ]
    xlsx_2001 = _build_xlsx(too_many_rows, headers=TEMPLATE_HEADERS)
    resp_limit = _upload_xlsx(client, staff_headers, xlsx_2001, "over_2000.xlsx")
    assert resp_limit.status_code == 400

    assert db_session.scalar(select(func.count(Applicant.id))) == 0
    assert db_session.scalar(select(func.count(ImportBatch.id))) == 0


def test_list_import_batches_pagination_and_operator_name(
    client, db_session, make_staff, make_auth_headers
):
    """GET /api/import/batches 分页倒序返回导入历史，并附带 operator_name 与 failures。"""
    staff_a = make_staff("op_a", role="staff", real_name="Alice Santos")
    staff_b = make_staff("op_b", role="admin", real_name="Bob Reyes")
    headers_a = make_auth_headers(staff_a)
    headers_b = make_auth_headers(staff_b)

    xlsx1 = _build_xlsx([["U1", None, "L1", "09171000001"]], headers=TEMPLATE_HEADERS)
    xlsx2 = _build_xlsx([["U2", None, "L2", "bad-phone"]], headers=TEMPLATE_HEADERS)
    xlsx3 = _build_xlsx([["U3", None, "L3", "09171000003"]], headers=TEMPLATE_HEADERS)

    assert _upload_xlsx(client, headers_a, xlsx1, "first.xlsx").status_code == 200
    assert _upload_xlsx(client, headers_b, xlsx2, "second.xlsx").status_code == 200
    assert _upload_xlsx(client, headers_a, xlsx3, "third.xlsx").status_code == 200

    page1 = client.get(
        BATCHES_URL, params={"page": 1, "page_size": 2}, headers=headers_a
    )
    assert page1.status_code == 200
    d1 = page1.json()["data"]
    assert d1["total"] == 3
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert len(d1["items"]) == 2
    assert d1["items"][0]["file_name"] == "third.xlsx"
    assert d1["items"][0]["operator_name"] == "Alice Santos"
    assert d1["items"][0]["failures"] == []
    assert d1["items"][1]["file_name"] == "second.xlsx"
    assert d1["items"][1]["operator_name"] == "Bob Reyes"
    assert d1["items"][1]["fail_count"] == 1
    assert len(d1["items"][1]["failures"]) == 1
    assert d1["items"][1]["failures"][0]["row"] == 2

    page2 = client.get(
        BATCHES_URL, params={"page": 2, "page_size": 2}, headers=headers_a
    )
    assert page2.status_code == 200
    d2 = page2.json()["data"]
    assert len(d2["items"]) == 1
    assert d2["items"][0]["file_name"] == "first.xlsx"
    assert d2["items"][0]["operator_name"] == "Alice Santos"
