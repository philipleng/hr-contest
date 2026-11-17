"""SUB 组 P0 用例：提交链路与手机号预检

编号对应「最小测试集 · SUB 组」。断言基于现有实现；
与预期不一致或属于刻意锁定当前行为的地方，在 docstring 中标注「锁定现状」。
"""

from sqlalchemy import func, select

from app.models import Applicant, StatusHistory
from app.utils.tz import now_local

SUBMIT = "/api/applicant/submit"
CHECK_PHONE = "/api/applicant/check-phone"


def _count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(Applicant)) or 0


def test_sub_01_minimal_submit(client, db_session, submit_payload):
    """SUB-01 最小合法提交：200 + DB 来源/同意时间落库"""
    resp = client.post(SUBMIT, json=submit_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "Submitted."
    applicant_id = body["data"]["applicant_id"]
    assert applicant_id > 0

    row = db_session.get(Applicant, applicant_id)
    assert row is not None
    assert row.phone == "09171234567"
    assert row.status == "new"
    assert row.source_type == "self"
    assert row.source_ref is None
    assert row.created_by is None
    assert row.privacy_agreed_at is not None


def test_sub_02_phone_normalized(client, db_session, submit_payload):
    """SUB-02 手机号归一化：+63 917-123-4567 → 09171234567"""
    resp = client.post(SUBMIT, json=submit_payload(phone="+63 917-123-4567"))

    assert resp.status_code == 200
    row = db_session.get(Applicant, resp.json()["data"]["applicant_id"])
    assert row.phone == "09171234567"


def test_sub_03_duplicate_phone(client, db_session, submit_payload):
    """SUB-03 重复手机号：首次 200，再次 409，库里仅 1 条未删除记录"""
    first = client.post(SUBMIT, json=submit_payload())
    assert first.status_code == 200

    second = client.post(SUBMIT, json=submit_payload())

    assert second.status_code == 409
    assert second.json() == {
        "detail": "This mobile number has already applied. "
        "Please contact our staff if you need to update it."
    }
    assert _count(db_session) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Applicant).where(
            Applicant.phone == "09171234567", Applicant.deleted_at.is_(None),
        )
    ) == 1


def test_sub_04_resubmit_after_soft_delete(client, db_session, submit_payload):
    """SUB-04 软删后同号可重申：新 id ≠ 旧 id，旧记录 deleted_at 非空"""
    first = client.post(SUBMIT, json=submit_payload())
    assert first.status_code == 200
    old_id = first.json()["data"]["applicant_id"]

    old = db_session.get(Applicant, old_id)
    old.deleted_at = now_local()
    db_session.commit()

    second = client.post(SUBMIT, json=submit_payload())
    assert second.status_code == 200
    new_id = second.json()["data"]["applicant_id"]

    assert new_id != old_id
    db_session.refresh(old)
    assert old.deleted_at is not None
    assert _count(db_session) == 2


def test_sub_05_privacy_not_agreed(client, db_session, submit_payload):
    """SUB-05 未同意隐私：422，库中无新增"""
    resp = client.post(SUBMIT, json=submit_payload(privacy_agreed=False))

    assert resp.status_code == 422
    assert "privacy" in resp.text.lower()
    assert _count(db_session) == 0


def test_sub_06_missing_name(client, db_session, submit_payload):
    """SUB-06 缺姓或名：422，库中无新增"""
    for missing in ("first_name", "last_name"):
        payload = submit_payload()
        payload.pop(missing)
        resp = client.post(SUBMIT, json=payload)
        assert resp.status_code == 422, missing
        assert missing in resp.text

    assert _count(db_session) == 0


def test_sub_07_invalid_phone(client, db_session, submit_payload):
    """SUB-07 手机号格式非法：422，提示含 valid mobile number"""
    resp = client.post(SUBMIT, json=submit_payload(phone="12345"))

    assert resp.status_code == 422
    assert "valid mobile number" in resp.text
    assert _count(db_session) == 0


def test_sub_08_forged_source_type(client, db_session, submit_payload):
    """SUB-08 客户端伪造 source_type：200，入库仍为 self"""
    resp = client.post(SUBMIT, json=submit_payload(source_type="staff"))

    assert resp.status_code == 200
    row = db_session.get(Applicant, resp.json()["data"]["applicant_id"])
    assert row.source_type == "self"
    assert row.source_ref is None
    assert row.created_by is None


def test_sub_09_referral_source(client, db_session, submit_payload):
    """SUB-09 无 token + 推广码：source_type=referral，source_ref 原样保留"""
    resp = client.post(SUBMIT, json=submit_payload(source_ref="promo01"))

    assert resp.status_code == 200
    row = db_session.get(Applicant, resp.json()["data"]["applicant_id"])
    assert row.source_type == "referral"
    assert row.source_ref == "promo01"
    assert row.created_by is None


def test_sub_10_staff_proxy_submit(
    client, db_session, submit_payload, make_staff, make_auth_headers,
):
    """SUB-10 员工 token 代录：source_type=staff，来源与操作人由服务端写入"""
    staff = make_staff(username="staff10")

    resp = client.post(
        SUBMIT, json=submit_payload(), headers=make_auth_headers(staff),
    )

    assert resp.status_code == 200
    row = db_session.get(Applicant, resp.json()["data"]["applicant_id"])
    assert row.source_type == "staff"
    assert row.source_ref == staff.username
    assert row.created_by == staff.id


def test_sub_11_first_status_history(client, db_session, submit_payload):
    """SUB-11 首条状态流水：仅 1 条，from_status 为空、to_status=new"""
    resp = client.post(SUBMIT, json=submit_payload())
    assert resp.status_code == 200
    applicant_id = resp.json()["data"]["applicant_id"]

    rows = db_session.scalars(
        select(StatusHistory).where(StatusHistory.applicant_id == applicant_id)
    ).all()

    assert len(rows) == 1
    history = rows[0]
    assert history.from_status is None
    assert history.to_status == "new"
    assert history.operator_id is None
    assert history.note == "First entry"


def test_sub_12_submit_rate_limit(client, db_session, submit_payload):
    """SUB-12 提交限流（P1）：同 IP 连发 6 次，前 5 次 200，第 6 次 429"""
    phones = [f"0917123450{i}" for i in range(6)]

    codes = [
        client.post(SUBMIT, json=submit_payload(phone=phone)).status_code
        for phone in phones
    ]

    assert codes[:5] == [200] * 5
    assert codes[5] == 429
    assert _count(db_session) == 5

    sixth = client.post(SUBMIT, json=submit_payload(phone=phones[5]))
    assert sixth.json() == {
        "detail": "Too many requests. Please wait a minute and try again."
    }


def test_sub_13_gender_optional(client, db_session, submit_payload):
    """SUB-13 gender 可选性（P1）：锁定现状——不传 gender 也能提交成功"""
    resp = client.post(SUBMIT, json=submit_payload())

    assert resp.status_code == 200
    row = db_session.get(Applicant, resp.json()["data"]["applicant_id"])
    assert row.gender is None


def test_sub_14_check_phone_no_leak(client, db_session, submit_payload):
    """SUB-14 check-phone 不泄露：两种号码都 200，响应只有 exists"""
    created = client.post(
        SUBMIT, json=submit_payload(phone="09171234567", first_name="LeakTest"),
    )
    assert created.status_code == 200

    existing = client.post(CHECK_PHONE, json={"phone": "+63 917-123-4567"})
    missing = client.post(CHECK_PHONE, json={"phone": "09179999999"})

    assert existing.status_code == 200
    assert existing.json()["data"] == {"exists": True}
    assert missing.status_code == 200
    assert missing.json()["data"] == {"exists": False}

    for resp in (existing, missing):
        assert set(resp.json()["data"]) == {"exists"}
        assert "LeakTest" not in resp.text
        assert "applicant_id" not in resp.text
