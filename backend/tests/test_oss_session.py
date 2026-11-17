"""上传会话：STS 收紧、令牌防篡改/过期、员工不限流"""

import time

from app.config import settings
from app.utils import upload_session
from app.utils.oss import STS_TTL_SECONDS, build_sts_policy


def _fake_sts(prefix: str) -> dict:
    return {
        "access_key_id": "ak",
        "access_key_secret": "sk",
        "security_token": "token",
        "expiration": "2026-11-15T00:00:00+00:00",
        "bucket": "bkt",
        "region": "ap-southeast-6",
        "endpoint": "",
    }


def test_session_unavailable_without_oss(client):
    resp = client.post("/api/oss/session")

    assert resp.status_code == 503


def test_session_staff_unlimited(client, staff_headers):
    for _ in range(30):
        assert client.post("/api/oss/session", headers=staff_headers).status_code == 503

    for _ in range(10):
        assert client.post("/api/oss/session").status_code == 503
    assert client.post("/api/oss/session").status_code == 429


def test_session_returns_token_and_sts(client, monkeypatch):
    import app.routers.oss as oss_router

    monkeypatch.setattr(settings, "OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setattr(settings, "OSS_BUCKET", "bkt")
    monkeypatch.setattr(oss_router, "generate_sts_token", _fake_sts)

    resp = client.post("/api/oss/session")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_key_id"] == "ak"
    assert data["session_token"]
    assert data["prefix"].startswith("hr/") and data["prefix"].endswith("/")
    session_id = data["prefix"].removeprefix("hr/").removesuffix("/")
    assert len(session_id) == 16


def test_sts_policy_scoped_and_no_invalid_condition():
    policy = build_sts_policy("bkt", "hr/abc/")
    statement = policy["Statement"][0]

    assert statement["Resource"] == ["acs:oss:*:*:bkt/hr/abc/*"]
    assert statement["Action"] == ["oss:PutObject", "oss:AbortMultipartUpload"]
    # RAM/STS AssumeRole Policy 不支持 oss:ContentLengthRange（仅 OSS PostObject 支持），
    # 携带该 Condition 会导致阿里云 STS 返回 InvalidParameter.PolicyGrammar；
    # 单文件大小改由 Nginx client_max_body_size 与后端配额控制。
    assert "Condition" not in statement
    assert STS_TTL_SECONDS == 900


def test_verify_rejects_tamper_and_expiry():
    token, prefix = upload_session.new_upload_session()
    assert upload_session.verify_upload_session(token) == prefix

    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert upload_session.verify_upload_session(tampered) is None
    assert upload_session.verify_upload_session(None) is None

    session_id, _, _ = token.split(".")
    past = int(time.time()) - 10
    expired = f"{session_id}.{past:x}.{upload_session._mac(session_id, past)}"
    assert upload_session.verify_upload_session(expired) is None
