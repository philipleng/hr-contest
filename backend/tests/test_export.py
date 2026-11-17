"""EXP 组 P0 用例：申请人导出（xlsx 内容、筛选、权限、默认脱敏、审计日志、截断治理）

编号对应「最小测试集 · EXP 组」。xlsx 用 openpyxl 解析内存流，不启动浏览器。
状态列导出为英文展示名（contacted → Contacted），属现有实现，断言按此锁定。
"""

import logging
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import insert

from app.models import Applicant
from app.routers.export import EXPORT_MAX_ROWS, safe_cell

EXPORT = "/api/export/applicant"

EXPECTED_HEADERS = [
    "ID", "Name", "Gender", "Birth Date", "Nationality", "Marital Status",
    "Mobile", "Alternate No.", "Email", "City", "Barangay", "Home Province",
    "FB Link", "FB Name", "TikTok",
    "ID 1 Type", "ID 1 Number", "NBI",
    "Target Job", "Expected Monthly Salary (PHP)", "Available Time", "Work Type",
    "Preferred Location", "Live-in",
    "Education", "English Level", "Chinese Level", "Last Job", "Work Experience",
    "Source", "Source Ref", "Referrer Phone",
    "Status", "Actual Salary (PHP)", "Employer", "Hired Date", "Internal Notes",
    "Created At",
]
COL = {name: idx for idx, name in enumerate(EXPECTED_HEADERS)}


def _read(resp):
    """解析导出的 xlsx，返回 (工作表标题, 全部行)"""
    wb = load_workbook(BytesIO(resp.content), read_only=True)
    ws = wb.active
    return ws.title, list(ws.iter_rows(values_only=True))


def _submit(client, payload):
    resp = client.post("/api/applicant/submit", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_exp_01_headers(client, admin_headers, submit_payload):
    """EXP-01 表头完整：38 列，名称/顺序与 headers 定义一致"""
    _submit(client, submit_payload())

    resp = client.get(EXPORT, headers=admin_headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["x-export-truncated"] == "false"
    assert resp.headers["x-export-max-rows"] == str(EXPORT_MAX_ROWS)
    assert "X-Export-Truncated" in resp.headers["access-control-expose-headers"]
    assert "X-Export-Max-Rows" in resp.headers["access-control-expose-headers"]

    title, rows = _read(resp)
    assert title == "Applicants"
    assert len(rows[0]) == 38
    assert list(rows[0]) == EXPECTED_HEADERS


def test_exp_02_rows_match_db(client, db_session, admin_headers, submit_payload):
    """EXP-02 数据行与库一致：2 条记录 → 1 表头 + 2 数据行（默认手机号掩码）"""
    id_new = _submit(client, submit_payload(
        first_name="Ana", last_name="Santos", phone="09171111111",
    ))
    id_contacted = _submit(client, submit_payload(
        first_name="Ben", last_name="Reyes", phone="09172222222",
    ))
    db_session.get(Applicant, id_contacted).status = "contacted"
    db_session.commit()

    resp = client.get(EXPORT, headers=admin_headers)
    _, rows = _read(resp)

    assert len(rows) == 3
    by_id = {row[COL["ID"]]: row for row in rows[1:]}
    assert set(by_id) == {id_new, id_contacted}
    assert by_id[id_new][COL["Name"]] == "Ana Santos"
    assert by_id[id_new][COL["Mobile"]] == "0917****111"
    assert by_id[id_new][COL["Status"]] == "New"
    assert by_id[id_contacted][COL["Name"]] == "Ben Reyes"
    assert by_id[id_contacted][COL["Mobile"]] == "0917****222"
    assert by_id[id_contacted][COL["Status"]] == "Contacted"


def test_exp_03_status_filter(client, db_session, admin_headers, submit_payload):
    """EXP-03 状态筛选：仅导出匹配状态"""
    id_new = _submit(client, submit_payload(phone="09173333331"))
    id_contacted = _submit(client, submit_payload(phone="09173333332"))
    db_session.get(Applicant, id_contacted).status = "contacted"
    db_session.commit()

    resp = client.get(EXPORT, params={"status": "contacted"}, headers=admin_headers)
    _, rows = _read(resp)

    assert len(rows) == 2
    assert rows[1][COL["ID"]] == id_contacted
    assert rows[1][COL["Status"]] == "Contacted"
    assert id_new not in {row[COL["ID"]] for row in rows[1:]}


def test_exp_04_source_filter(client, admin_headers, submit_payload):
    """EXP-04 来源筛选：仅导出 matching source_type"""
    id_self = _submit(client, submit_payload(phone="09174444441"))
    id_referral = _submit(client, submit_payload(
        phone="09174444442", source_ref="promo01",
    ))

    resp = client.get(EXPORT, params={"source_type": "referral"}, headers=admin_headers)
    _, rows = _read(resp)

    assert len(rows) == 2
    assert rows[1][COL["ID"]] == id_referral
    assert rows[1][COL["Source"]] == "Referral"
    assert rows[1][COL["Source Ref"]] == "promo01"
    assert id_self not in {row[COL["ID"]] for row in rows[1:]}


def test_exp_05_keyword_normalizes_phone(client, admin_headers, submit_payload):
    """EXP-05 关键字筛选：0917-123-4567 能命中库中 09171234567"""
    applicant_id = _submit(client, submit_payload(phone="09171234567"))

    resp = client.get(EXPORT, params={"keyword": "0917-123-4567"}, headers=admin_headers)
    _, rows = _read(resp)

    assert len(rows) == 2
    assert rows[1][COL["ID"]] == applicant_id
    assert rows[1][COL["Mobile"]] == "0917****567"


def test_exp_06_date_range(client, db_session, admin_headers):
    """EXP-06 日期区间（P1）：区间内出现、区间外不出现，含 end_date 23:59:59 半开边界"""
    inside = Applicant(
        first_name="Feb", last_name="Inside", phone="09175555551",
        created_at=datetime(2026, 2, 15, 10, 0),
    )
    end_edge = Applicant(
        first_name="FebEnd", last_name="Inside", phone="09175555554",
        created_at=datetime(2026, 2, 28, 23, 59, 59),
    )
    before = Applicant(
        first_name="Jan", last_name="Before", phone="09175555552",
        created_at=datetime(2026, 1, 10, 10, 0),
    )
    after = Applicant(
        first_name="Mar", last_name="After", phone="09175555553",
        created_at=datetime(2026, 3, 1, 0, 0, 0),
    )
    db_session.add_all([inside, end_edge, before, after])
    db_session.commit()

    resp = client.get(
        EXPORT,
        params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        headers=admin_headers,
    )
    _, rows = _read(resp)

    exported_ids = {row[COL["ID"]] for row in rows[1:]}
    assert exported_ids == {inside.id, end_edge.id}
    assert before.id not in exported_ids
    assert after.id not in exported_ids


@pytest.mark.slow
def test_exp_07_export_row_limit(client, db_session, admin_headers):
    """EXP-07 万行上限（P1，slow）：10,005 条导出 10,000 条 + 截断响应头与末行提示"""
    db_session.execute(
        insert(Applicant),
        [
            {
                "first_name": f"Bulk{i}",
                "last_name": "Applicant",
                "phone": f"0917{i:07d}",
                "status": "new",
                "source_type": "self",
            }
            for i in range(1, 10006)
        ],
    )
    db_session.commit()

    resp = client.get(EXPORT, headers=admin_headers)

    assert resp.status_code == 200
    assert resp.headers["x-export-truncated"] == "true"
    assert resp.headers["x-export-max-rows"] == str(EXPORT_MAX_ROWS)
    assert "X-Export-Truncated" in resp.headers["access-control-expose-headers"]
    assert "X-Export-Max-Rows" in resp.headers["access-control-expose-headers"]

    _, rows = _read(resp)
    # 表头 + 上限行数 + 末尾截断提示行
    assert len(rows) == EXPORT_MAX_ROWS + 2
    notice_row = rows[-1]
    assert notice_row[0] is not None
    assert "truncated" in notice_row[0].lower()
    assert str(EXPORT_MAX_ROWS) in notice_row[0]


def test_exp_08_formula_injection(client, admin_headers, submit_payload):
    """EXP-08 公式注入转义：姓名以 = 开头 → 单元格值前置单引号"""
    applicant_id = _submit(client, submit_payload(
        first_name=" =SUM(1,1)", last_name="Injected", phone="09176666661",
    ))

    resp = client.get(EXPORT, headers=admin_headers)
    _, rows = _read(resp)

    row = next(r for r in rows[1:] if r[COL["ID"]] == applicant_id)
    assert row[COL["Name"]].startswith("'")
    # 姓名首段原样保留前导空格，safe_cell 的 lstrip 判定后整体前置单引号
    assert row[COL["Name"]] == "' =SUM(1,1) Injected"
    # 直接用 safe_cell 复核纯函数行为（含前导空白绕过场景）
    assert safe_cell(" =SUM(1,1)") == "' =SUM(1,1)"
    assert safe_cell("plain") == "plain"


def test_exp_09_staff_forbidden(client, staff_headers):
    """EXP-09 staff 禁止导出：403，无文件流"""
    resp = client.get(EXPORT, headers=staff_headers)

    assert resp.status_code == 403
    assert resp.json() == {"detail": "You do not have permission for this action."}
    assert "content-disposition" not in resp.headers
    assert resp.headers["content-type"].startswith("application/json")


def test_exp_10_anonymous_forbidden(client):
    """EXP-10 未登录禁止导出：401，无文件流"""
    resp = client.get(EXPORT)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Authorization header."}
    assert "content-disposition" not in resp.headers
    assert resp.headers["content-type"].startswith("application/json")


def test_exp_11_pii_masked_by_default(client, admin_headers, submit_payload):
    """EXP-11 默认导出 PII 掩码脱敏：手机号、证件号、邮箱、社交、出生日期、推荐人均掩码，gender 保持可空"""
    applicant_id = _submit(client, submit_payload(
        phone="09171234567",
        phone_alt="09187654321",
        birth_date="1995-08-20",
        gender=None,
        id1_type="Passport",
        id1_number="P1234567",
        email="juan@example.com",
        fb_profile_url="https://www.facebook.com/juan.delacruz",
        fb_name="Juan Cruz",
        tiktok_username="@juantok",
        referrer_phone="09199998888",
    ))

    resp = client.get(EXPORT, headers=admin_headers)
    assert resp.status_code == 200
    _, rows = _read(resp)

    row = next(r for r in rows[1:] if r[COL["ID"]] == applicant_id)
    assert row[COL["Gender"]] is None
    assert row[COL["Birth Date"]] == "1995-**-**"
    assert row[COL["Mobile"]] == "0917****567"
    assert row[COL["Alternate No."]] == "0918****321"
    assert row[COL["Email"]] == "j***@example.com"
    assert row[COL["FB Link"]] == "https://www.facebook.com/***"
    assert row[COL["FB Name"]] == "J***"
    assert row[COL["TikTok"]] == "'@j***"
    assert row[COL["ID 1 Type"]] == "Passport"
    assert row[COL["ID 1 Number"]] == "P1****67"
    assert row[COL["Referrer Phone"]] == "0919****888"


def test_exp_12_include_pii_admin_and_non_admin_forbidden(
    client, admin_headers, staff_headers, make_staff, submit_payload,
):
    """EXP-12 include_pii=true 仅 admin 可导出明文；非 admin 返回 403"""
    from app.main import app
    from app.routers.applicant import require_admin

    applicant_id = _submit(client, submit_payload(
        phone="09171234567",
        phone_alt="09187654321",
        birth_date="1995-08-20",
        id1_type="Passport",
        id1_number="P1234567",
        email="juan@example.com",
        fb_profile_url="https://www.facebook.com/juan.delacruz",
        fb_name="Juan Cruz",
        tiktok_username="@juantok",
        referrer_phone="09199998888",
    ))

    # 1) admin 显式传 include_pii=true → 返回明文
    ok = client.get(EXPORT, params={"include_pii": "true"}, headers=admin_headers)
    assert ok.status_code == 200
    _, rows = _read(ok)
    row = next(r for r in rows[1:] if r[COL["ID"]] == applicant_id)
    assert row[COL["Birth Date"]] == "1995-08-20"
    assert row[COL["Mobile"]] == "09171234567"
    assert row[COL["Alternate No."]] == "09187654321"
    assert row[COL["Email"]] == "juan@example.com"
    assert row[COL["FB Link"]] == "https://www.facebook.com/juan.delacruz"
    assert row[COL["FB Name"]] == "Juan Cruz"
    assert row[COL["TikTok"]] == "'@juantok"
    assert row[COL["ID 1 Number"]] == "P1234567"
    assert row[COL["Referrer Phone"]] == "09199998888"

    # 2) staff 传 include_pii=true → 403
    forbidden = client.get(EXPORT, params={"include_pii": "true"}, headers=staff_headers)
    assert forbidden.status_code == 403

    # 3) 即使绕过外层依赖校验，函数内角色守卫仍拦截非 admin 明文导出
    non_admin = make_staff("export_guard_staff", role="staff")
    app.dependency_overrides[require_admin] = lambda: non_admin
    try:
        guarded = client.get(EXPORT, params={"include_pii": "true"})
        assert guarded.status_code == 403
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_exp_13_audit_log_redacts_keyword_and_pii(
    client, admin_headers, submit_payload, caplog,
):
    """EXP-13 导出审计日志：记录操作人/筛选摘要/include_pii/条数/截断标记，禁止记录明文 keyword"""
    _submit(client, submit_payload(
        first_name="AuditSecretName",
        phone="09178887777",
        id1_number="ID-99887766",
    ))

    caplog.set_level(logging.INFO, logger="app.routers.export")
    caplog.clear()

    resp = client.get(
        EXPORT,
        params={"status": "new", "keyword": "09178887777"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    assert len(caplog.records) == 1
    log_msg = caplog.records[0].getMessage()
    assert "applicant_export" in log_msg
    assert "username=admin_case" in log_msg
    assert "role=admin" in log_msg
    assert "include_pii=False" in log_msg
    assert "row_count=1" in log_msg
    assert "truncated=False" in log_msg
    assert "'has_keyword': True" in log_msg
    # 严禁将 keyword、手机号、证件号明文写入日志
    assert "09178887777" not in log_msg
    assert "ID-99887766" not in log_msg
    assert "AuditSecretName" not in log_msg


def test_exp_14_availability_and_intent_tag_filters(
    client, db_session, admin_headers, submit_payload, caplog,
):
    """EXP-14 导出支持 availability 与 intent_tag 筛选（'bpo' 不误匹配 'bpo-night'），并记录审计日志"""
    id_match = _submit(client, submit_payload(phone="09179000001", first_name="Match"))
    id_other_avail = _submit(client, submit_payload(phone="09179000002", first_name="OtherAvail"))
    id_bpo_night = _submit(client, submit_payload(phone="09179000003", first_name="NightOnly"))

    db_session.get(Applicant, id_match).availability = 1
    db_session.get(Applicant, id_match).intent_tags = "cashier,bpo"
    db_session.get(Applicant, id_other_avail).availability = 2
    db_session.get(Applicant, id_other_avail).intent_tags = "bpo"
    db_session.get(Applicant, id_bpo_night).availability = 1
    db_session.get(Applicant, id_bpo_night).intent_tags = "bpo-night"
    db_session.commit()

    caplog.set_level(logging.INFO, logger="app.routers.export")
    caplog.clear()

    # 1) 仅 intent_tag=bpo：命中 id_match 和 id_other_avail，排除 bpo-night
    resp_tag = client.get(EXPORT, params={"intent_tag": "bpo"}, headers=admin_headers)
    assert resp_tag.status_code == 200
    _, rows_tag = _read(resp_tag)
    assert {r[COL["ID"]] for r in rows_tag[1:]} == {id_match, id_other_avail}

    # 2) availability=1 + intent_tag=bpo：仅命中 id_match
    caplog.clear()
    resp_combo = client.get(
        EXPORT, params={"availability": 1, "intent_tag": "bpo"}, headers=admin_headers,
    )
    assert resp_combo.status_code == 200
    _, rows_combo = _read(resp_combo)
    assert [r[COL["ID"]] for r in rows_combo[1:]] == [id_match]

    assert len(caplog.records) == 1
    log_msg = caplog.records[0].getMessage()
    assert "'availability': 1" in log_msg
    assert "'intent_tag': 'bpo'" in log_msg


def test_exp_15_write_only_styles_and_column_widths(
    client, admin_headers, submit_payload,
):
    """EXP-15 流式 write_only 导出保留表头样式与预计算列宽（<= 40）"""
    _submit(client, submit_payload(
        first_name="VeryLongFirstNameForWidthCalculationCheck",
        last_name="ApplicantWithLongSurname",
        address_city="Makati City Metro Manila Philippines Extra Long",
        phone="09179111111",
    ))

    resp = client.get(EXPORT, headers=admin_headers)
    assert resp.status_code == 200

    wb = load_workbook(BytesIO(resp.content))
    ws = wb.active
    assert ws.title == "Applicants"

    # 38 列均有预计算列宽且受限于 (0, 40]
    for col_idx in range(1, len(EXPECTED_HEADERS) + 1):
        col_letter = get_column_letter(col_idx)
        width = ws.column_dimensions[col_letter].width
        assert width is not None and 0 < width <= 40

    # 超长内容列宽被上限 40 截断
    assert ws.column_dimensions[get_column_letter(COL["Name"] + 1)].width == 40
    assert ws.column_dimensions[get_column_letter(COL["City"] + 1)].width == 40

    # Row 1 表头样式（409EFF 填充、FFFFFF 加粗字体、居中对齐）
    for col_idx, expected_header in enumerate(EXPECTED_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx)
        assert cell.value == expected_header
        assert cell.fill.fill_type == "solid"
        assert cell.fill.start_color.rgb.endswith("409EFF")
        assert cell.font.bold is True
        assert cell.font.size == 12
        assert cell.font.color.rgb.endswith("FFFFFF")
        assert cell.alignment.horizontal == "center"
        assert cell.alignment.vertical == "center"


def test_exp_16_formula_injection_across_prefixes_and_columns(
    client, db_session, admin_headers, submit_payload,
):
    """EXP-16 全前缀（= + - @ 含前导空白）在多列中的公式注入均被转义"""
    applicant_id = _submit(client, submit_payload(
        first_name="=CMD()",
        last_name="User",
        phone="09179222222",
        address_city=" +SUM(A1:A2)",
        target_job="\t-HYPERLINK(\"http://evil\")",
        last_job=" @IMPORTXML()",
    ))
    applicant = db_session.get(Applicant, applicant_id)
    applicant.employer = "-1+1"
    applicant.internal_remark = "  @evil"
    db_session.commit()

    resp = client.get(EXPORT, headers=admin_headers)
    assert resp.status_code == 200
    _, rows = _read(resp)

    row = next(r for r in rows[1:] if r[COL["ID"]] == applicant_id)
    assert row[COL["Name"]] == "'=CMD() User"
    assert row[COL["City"]] == "' +SUM(A1:A2)"
    assert row[COL["Target Job"]] == "'\t-HYPERLINK(\"http://evil\")"
    assert row[COL["Last Job"]] == "' @IMPORTXML()"
    assert row[COL["Employer"]] == "'-1+1"
    assert row[COL["Internal Notes"]] == "'  @evil"


def test_exp_17_multi_batch_sample_and_stream_order(
    client, db_session, admin_headers,
):
    """EXP-17 超过 100 行采样边界（108 行）时，前 100 行与后续流式行顺序及内容完全一致"""
    base_time = datetime(2026, 5, 1, 8, 0, 0)
    total = 108
    db_session.execute(
        insert(Applicant),
        [
            {
                "first_name": f"Batch{i:03d}",
                "last_name": "Tester",
                "phone": f"0918{i:07d}",
                "status": "new",
                "source_type": "self",
                "created_at": base_time + timedelta(minutes=i),
            }
            for i in range(1, total + 1)
        ],
    )
    db_session.commit()

    resp = client.get(EXPORT, headers=admin_headers)
    assert resp.status_code == 200

    wb = load_workbook(BytesIO(resp.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == total + 1

    # 导出按 created_at DESC 排序：第 1 条数据为 Batch108，第 100 条为 Batch009，第 108 条为 Batch001
    data_rows = rows[1:]
    expected_names = [f"Batch{i:03d} Tester" for i in range(total, 0, -1)]
    assert [r[COL["Name"]] for r in data_rows] == expected_names
    assert data_rows[0][COL["Mobile"]] == "0918****108"
    assert data_rows[99][COL["Mobile"]] == "0918****009"
    assert data_rows[100][COL["Mobile"]] == "0918****008"
    assert data_rows[-1][COL["Mobile"]] == "0918****001"


def test_exp_18_truncation_notice_row_styles(
    client, db_session, admin_headers, monkeypatch,
):
    """EXP-18 截断提示行保留 FFF3CD 背景与 B45309 加粗字体，且仅第 1 列有文案"""
    monkeypatch.setattr("app.routers.export.EXPORT_MAX_ROWS", 3)
    base_time = datetime(2026, 5, 2, 8, 0, 0)
    db_session.execute(
        insert(Applicant),
        [
            {
                "first_name": f"Trunc{i}",
                "last_name": "Row",
                "phone": f"0919{i:07d}",
                "status": "new",
                "source_type": "self",
                "created_at": base_time + timedelta(minutes=i),
            }
            for i in range(1, 6)
        ],
    )
    db_session.commit()

    resp = client.get(EXPORT, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["x-export-truncated"] == "true"
    assert resp.headers["x-export-max-rows"] == "3"

    wb = load_workbook(BytesIO(resp.content))
    ws = wb.active
    assert ws.max_row == 5  # 1 表头 + 3 数据行 + 1 截断提示行

    notice_row_idx = ws.max_row
    notice_val = ws.cell(row=notice_row_idx, column=1).value
    assert notice_val is not None
    assert "truncated at 3 rows" in notice_val.lower()
    for col_idx in range(1, len(EXPECTED_HEADERS) + 1):
        cell = ws.cell(row=notice_row_idx, column=col_idx)
        if col_idx > 1:
            assert cell.value is None
        assert cell.fill.fill_type == "solid"
        assert cell.fill.start_color.rgb.endswith("FFF3CD")
        assert cell.font.bold is True
        assert cell.font.color.rgb.endswith("B45309")
