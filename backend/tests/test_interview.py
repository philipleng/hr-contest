"""面试记录接口与申请人全字段编辑契约用例"""

from datetime import datetime

from app.models import Applicant, InterviewRecord

SUBMIT = "/api/applicant/submit"
INTERVIEWS = "/api/applicant/{}/interviews"
APPLICANT_DETAIL = "/api/applicant/{}"


def _create_applicant(client, submit_payload, phone: str = "09171239001") -> int:
    resp = client.post(SUBMIT, json=submit_payload(phone=phone))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_interviews_require_login(client, submit_payload):
    """未登录访问面试记录读写接口应被拒绝"""
    applicant_id = _create_applicant(client, submit_payload, "09171239002")

    assert client.get(INTERVIEWS.format(applicant_id)).status_code in (401, 403)
    assert client.post(
        INTERVIEWS.format(applicant_id),
        json={"round": 1, "result": "pass"},
    ).status_code in (401, 403)


def test_create_and_list_interviews_ordered(
    client, db_session, submit_payload, make_staff, make_auth_headers,
):
    """支持 1~3 轮创建，按 round 倒序、同轮次按创建时间/id 倒序读取并带操作人信息"""
    applicant_id = _create_applicant(client, submit_payload, "09171239003")
    hr1 = make_staff("hr_interviewer_1", real_name="Alice Santos")
    hr2 = make_staff("hr_interviewer_2", real_name="Bob Reyes")
    h1 = make_auth_headers(hr1)
    h2 = make_auth_headers(hr2)

    # 先创建 1 轮，再创建 3 轮，再创建两条 2 轮（验证排序而非插入序）
    r1 = client.post(
        INTERVIEWS.format(applicant_id),
        json={
            "round": 1,
            "interview_at": "2026-11-10T10:00:00",
            "result": "pass",
            "comment": "Good communication skills",
        },
        headers=h1,
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()["data"]
    assert d1["round"] == 1
    assert d1["result"] == "pass"
    assert d1["comment"] == "Good communication skills"
    assert d1["operator_id"] == hr1.id
    assert d1["operator_name"] == "Alice Santos"
    assert d1["interview_at"].startswith("2026-11-10T10:00:00")

    r3 = client.post(
        INTERVIEWS.format(applicant_id),
        json={
            "round": 3,
            "interview_at": "2026-11-14T15:30:00",
            "result": "pending",
            "comment": "   ",
        },
        headers=h2,
    )
    assert r3.status_code == 200, r3.text
    d3 = r3.json()["data"]
    assert d3["comment"] is None
    assert d3["operator_id"] == hr2.id
    assert d3["operator_name"] == "Bob Reyes"

    r2_first = client.post(
        INTERVIEWS.format(applicant_id),
        json={"round": 2, "result": "pending", "comment": "2nd round initial"},
        headers=h1,
    )
    assert r2_first.status_code == 200, r2_first.text

    r2_second = client.post(
        INTERVIEWS.format(applicant_id),
        json={"round": 2, "result": "fail", "comment": "2nd round follow-up"},
        headers=h2,
    )
    assert r2_second.status_code == 200, r2_second.text

    # 调整两条 2 轮记录的 created_at，确保时间倒序生效
    rec_2a = db_session.get(InterviewRecord, r2_first.json()["data"]["id"])
    rec_2b = db_session.get(InterviewRecord, r2_second.json()["data"]["id"])
    rec_2a.created_at = datetime(2026, 11, 11, 9, 0, 0)
    rec_2b.created_at = datetime(2026, 11, 12, 9, 0, 0)
    db_session.commit()

    listing = client.get(INTERVIEWS.format(applicant_id), headers=h1)
    assert listing.status_code == 200, listing.text
    items = listing.json()["data"]
    assert [item["id"] for item in items] == [
        d3["id"],
        r2_second.json()["data"]["id"],
        r2_first.json()["data"]["id"],
        d1["id"],
    ]
    assert [item["operator_name"] for item in items] == [
        "Bob Reyes",
        "Bob Reyes",
        "Alice Santos",
        "Alice Santos",
    ]


def test_interviews_404_when_missing_or_soft_deleted(
    client, db_session, submit_payload, admin_headers, staff_headers,
):
    """申请人不存在或已软删除时，POST/GET 均返回 404"""
    assert client.get(INTERVIEWS.format(999999), headers=staff_headers).status_code == 404
    assert client.post(
        INTERVIEWS.format(999999),
        json={"round": 1, "result": "pass"},
        headers=staff_headers,
    ).status_code == 404

    applicant_id = _create_applicant(client, submit_payload, "09171239004")
    del_resp = client.delete(APPLICANT_DETAIL.format(applicant_id), headers=admin_headers)
    assert del_resp.status_code == 200

    assert client.get(INTERVIEWS.format(applicant_id), headers=staff_headers).status_code == 404
    assert client.post(
        INTERVIEWS.format(applicant_id),
        json={"round": 1, "result": "pass"},
        headers=staff_headers,
    ).status_code == 404


def test_interviews_reject_invalid_round_or_result(client, submit_payload, staff_headers):
    """round 超出 1~3 或 result 不在枚举内返回 422"""
    applicant_id = _create_applicant(client, submit_payload, "09171239005")

    for bad_round in (0, 4):
        resp = client.post(
            INTERVIEWS.format(applicant_id),
            json={"round": bad_round, "result": "pass"},
            headers=staff_headers,
        )
        assert resp.status_code == 422

    resp_bad_result = client.post(
        INTERVIEWS.format(applicant_id),
        json={"round": 1, "result": "skip"},
        headers=staff_headers,
    )
    assert resp_bad_result.status_code == 422


def test_patch_applicant_full_fields_and_clear_to_none(
    client, db_session, submit_payload, staff_headers,
):
    """PATCH 全字段编辑落库，且传 null 或空串可清空选填字段"""
    applicant_id = _create_applicant(client, submit_payload, "09171239006")

    full_payload = {
        "first_name": "Maria",
        "middle_name": "Clara",
        "last_name": "Reyes",
        "gender": "female",
        "birth_date": "1996-05-12",
        "nationality": "Filipino",
        "marital_status": "single",
        "phone": "09178880001",
        "phone_alt": "09178880002",
        "email": "maria@example.com",
        "address_city": "Makati",
        "address_barangay": "Bel-Air",
        "home_province": "Laguna",
        "fb_profile_url": "https://facebook.com/maria.reyes",
        "fb_phone": "09178880003",
        "fb_name": "Maria Reyes",
        "tiktok_username": "@mariareyes",
        "id1_type": "Passport",
        "id1_number": "P1234567A",
        "id2_type": "UMID",
        "id2_number": "U9876543B",
        "id3_type": "PhilHealth",
        "id3_number": "PH11223344",
        "has_nbi": True,
        "nbi_valid_until": "2027-06-30",
        "target_job": "Customer Service",
        "expected_salary": 28000,
        "available_time": "anytime",
        "availability": 1,
        "available_from": "2026-12-01",
        "work_type": "fulltime",
        "preferred_location": "BGC / Makati",
        "intent_tags": "bpo,csr",
        "live_in_ok": False,
        "education": "College Graduate",
        "skills": ["English", "Typing"],
        "english_level": "fluent",
        "chinese_level": "basic",
        "last_job": "CSR at ABC Corp (2 years)",
        "work_experience": "Handled inbound calls and email support.",
        "applicant_remark": "Available for night shift.",
        "internal_remark": "Strong candidate.",
    }
    resp = client.patch(
        APPLICANT_DETAIL.format(applicant_id),
        json=full_payload,
        headers=staff_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["gender"] == "female"
    assert data["birth_date"] == "1996-05-12"
    assert data["marital_status"] == "single"
    assert data["expected_salary"] == 28000
    assert data["available_time"] == "anytime"
    assert data["available_from"] == "2026-12-01"
    assert data["work_type"] == "fulltime"
    assert data["preferred_location"] == "BGC / Makati"
    assert data["live_in_ok"] is False
    assert data["education"] == "College Graduate"
    assert data["english_level"] == "fluent"
    assert data["chinese_level"] == "basic"
    assert data["id1_type"] == "Passport"
    assert data["id2_number"] == "U9876543B"
    assert data["id3_type"] == "PhilHealth"
    assert data["has_nbi"] is True
    assert data["nbi_valid_until"] == "2027-06-30"
    assert data["fb_profile_url"] == "https://facebook.com/maria.reyes"
    assert data["tiktok_username"] == "@mariareyes"
    assert data["last_job"] == "CSR at ABC Corp (2 years)"
    assert data["work_experience"] == "Handled inbound calls and email support."

    # 1) 传空串清空带正则及文本类选填字段（含空白串）
    clear_by_empty_str = client.patch(
        APPLICANT_DETAIL.format(applicant_id),
        json={
            "middle_name": "",
            "gender": "",
            "nationality": "  ",
            "marital_status": "",
            "phone_alt": " ",
            "email": "",
            "address_city": "",
            "address_barangay": "",
            "home_province": "",
            "fb_profile_url": "",
            "fb_phone": "",
            "fb_name": "",
            "tiktok_username": "",
            "id1_type": "",
            "id1_number": "",
            "id2_type": "",
            "id2_number": "",
            "id3_type": "",
            "id3_number": "",
            "target_job": "",
            "available_time": "",
            "work_type": "",
            "preferred_location": "",
            "education": "",
            "english_level": "",
            "chinese_level": "",
            "last_job": "",
            "work_experience": "",
            "applicant_remark": "",
            "internal_remark": "",
        },
        headers=staff_headers,
    )
    assert clear_by_empty_str.status_code == 200, clear_by_empty_str.text

    # 2) 显式传 null 清空日期、数值、布尔及 gender 等可空列
    clear_by_null = client.patch(
        APPLICANT_DETAIL.format(applicant_id),
        json={
            "gender": None,
            "birth_date": None,
            "expected_salary": None,
            "available_from": None,
            "has_nbi": None,
            "nbi_valid_until": None,
            "live_in_ok": None,
        },
        headers=staff_headers,
    )
    assert clear_by_null.status_code == 200, clear_by_null.text

    detail = client.get(APPLICANT_DETAIL.format(applicant_id), headers=staff_headers)
    assert detail.status_code == 200
    after = detail.json()["data"]
    for cleared_field in (
        "middle_name",
        "gender",
        "birth_date",
        "nationality",
        "marital_status",
        "phone_alt",
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
        "has_nbi",
        "nbi_valid_until",
        "target_job",
        "expected_salary",
        "available_time",
        "available_from",
        "work_type",
        "preferred_location",
        "live_in_ok",
        "education",
        "english_level",
        "chinese_level",
        "last_job",
        "work_experience",
        "applicant_remark",
        "internal_remark",
    ):
        assert after[cleared_field] is None, f"{cleared_field} expected None, got {after[cleared_field]!r}"

    db_session.expire_all()
    row = db_session.get(Applicant, applicant_id)
    assert row.gender is None
    assert row.birth_date is None
    assert row.expected_salary is None
    assert row.available_from is None
    assert row.has_nbi is None
    assert row.nbi_valid_until is None
    assert row.live_in_ok is None


def test_patch_applicant_rejects_invalid_enums_including_gender_other(
    client, submit_payload, staff_headers,
):
    """gender='other' 以及非法 work_type/english_level/chinese_level 必须返回 422"""
    applicant_id = _create_applicant(client, submit_payload, "09171239007")

    for bad_payload in (
        {"gender": "other"},
        {"work_type": "freelance"},
        {"english_level": "native"},
        {"chinese_level": "advanced"},
    ):
        resp = client.patch(
            APPLICANT_DETAIL.format(applicant_id),
            json=bad_payload,
            headers=staff_headers,
        )
        assert resp.status_code == 422, f"{bad_payload} should 422, got {resp.status_code}"
