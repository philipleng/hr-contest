"""联系记录与今日待跟进用例"""

from datetime import datetime, timedelta

from app.models import ContactLog
from app.utils.tz import now_local

SUBMIT = "/api/applicant/submit"
CONTACTS = "/api/applicant/{}/contacts"
FOLLOW_UPS = "/api/contact/follow-ups"


def _create_applicant(client, submit_payload, phone: str) -> int:
    resp = client.post(SUBMIT, json=submit_payload(phone=phone))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_contacts_require_login(client, submit_payload):
    """未登录不能读写联系记录"""
    applicant_id = _create_applicant(client, submit_payload, "09171230001")

    assert client.get(CONTACTS.format(applicant_id)).status_code == 401
    assert client.get(FOLLOW_UPS).status_code == 401
    assert client.post(
        CONTACTS.format(applicant_id),
        json={"channel": "phone", "result": "reached"},
    ).status_code == 401


def test_create_and_list_contact(client, db_session, submit_payload, staff_headers):
    """新增联系记录落库，历史按时间倒序返回并带操作人"""
    applicant_id = _create_applicant(client, submit_payload, "09171230002")

    resp = client.post(
        CONTACTS.format(applicant_id),
        json={
            "channel": "phone",
            "result": "reached",
            "note": "Confirmed availability",
            "next_follow_at": "2026-11-20T09:30:00",
        },
        headers=staff_headers,
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["operator_name"] == "staff_case"

    row = db_session.get(ContactLog, data["id"])
    assert row.applicant_id == applicant_id
    assert row.operator_id is not None
    assert row.next_follow_at == datetime(2026, 11, 20, 9, 30)

    history = client.get(CONTACTS.format(applicant_id), headers=staff_headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.json()["data"]] == [data["id"]]


def test_follow_ups_only_latest_and_due(client, submit_payload, staff_headers):
    """待跟进只看每人最后一条记录，且只包含今天及逾期的"""
    due_id = _create_applicant(client, submit_payload, "09171230003")
    future_id = _create_applicant(client, submit_payload, "09171230004")

    client.post(
        CONTACTS.format(due_id),
        json={
            "channel": "phone",
            "result": "no_answer",
            "next_follow_at": (now_local() - timedelta(days=1)).isoformat(),
        },
        headers=staff_headers,
    )
    client.post(
        CONTACTS.format(future_id),
        json={
            "channel": "phone",
            "result": "no_answer",
            "next_follow_at": (now_local() + timedelta(days=1)).isoformat(),
        },
        headers=staff_headers,
    )

    resp = client.get(FOLLOW_UPS, headers=staff_headers)
    assert resp.status_code == 200
    assert [item["applicant_id"] for item in resp.json()["data"]] == [due_id]

    # 最新一条记录不再需要跟进 → 旧的逾期待办不再出现
    client.post(
        CONTACTS.format(due_id),
        json={"channel": "sms", "result": "reached"},
        headers=staff_headers,
    )
    resp = client.get(FOLLOW_UPS, headers=staff_headers)
    assert resp.json()["data"] == []


def test_contact_rejects_unknown_channel(client, submit_payload, staff_headers):
    """渠道/结果枚举以外的值直接 422"""
    applicant_id = _create_applicant(client, submit_payload, "09171230005")

    resp = client.post(
        CONTACTS.format(applicant_id),
        json={"channel": "telegram", "result": "reached"},
        headers=staff_headers,
    )

    assert resp.status_code == 422
