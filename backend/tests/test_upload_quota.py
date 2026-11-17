"""上传配额与水位：匿名受限、员工不限、磁盘保护"""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.utils import ratelimit


def _upload(client, headers=None, size=10, filename="photo.jpg", kind="media"):
    return client.post(
        "/api/oss/upload",
        files={"file": (filename, b"x" * size, "image/jpeg")},
        data={"kind": kind},
        headers=headers or {},
    )


@pytest.fixture()
def upload_dirs(tmp_path, monkeypatch):
    import app.routers.oss as oss_router

    media_dir = tmp_path / "uploads"
    resume_dir = tmp_path / "private_uploads"
    media_dir.mkdir()
    resume_dir.mkdir()
    monkeypatch.setattr(oss_router, "UPLOAD_DIR", str(media_dir))
    monkeypatch.setattr(oss_router, "PRIVATE_UPLOAD_DIR", str(resume_dir))
    return media_dir


def _phone(i: int) -> str:
    return f"0917{i:07d}"


def test_anon_daily_request_quota_exceeded(client, monkeypatch, upload_dirs):
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_REQUESTS", 2)

    assert _upload(client).status_code == 200
    assert _upload(client).status_code == 200
    resp = _upload(client)

    assert resp.status_code == 429


def test_anon_daily_byte_quota_exceeded(client, monkeypatch, upload_dirs):
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_REQUESTS", 50)
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_BYTES", 100)

    assert _upload(client, size=101).status_code == 200
    resp = _upload(client, size=1)

    assert resp.status_code == 429


def test_staff_upload_ignores_anon_quota(client, monkeypatch, upload_dirs, staff_headers):
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_REQUESTS", 1)
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_BYTES", 10)

    for _ in range(5):
        assert _upload(client, headers=staff_headers, size=100).status_code == 200

    # staff 不计入匿名桶：同 IP 的匿名额度仍然完整
    assert _upload(client, size=5).status_code == 200
    assert _upload(client, size=5).status_code == 429


def test_staff_1200_uploads_pass(client, upload_dirs, staff_headers):
    """扫楼极限：400 份申请 × 3 个文件，全部不能被拦截"""
    for _ in range(1200):
        assert _upload(client, headers=staff_headers, size=4).status_code == 200


def test_staff_submit_and_phone_check_unlimited(client, staff_headers):
    for i in range(6):
        resp = client.post(
            "/api/applicant/submit",
            json={
                "privacy_agreed": True,
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "phone": _phone(i),
            },
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text

    for _ in range(21):
        resp = client.post(
            "/api/applicant/check-phone",
            json={"phone": _phone(0)},
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text

    # 匿名同一 IP：第 6 次提交被限流
    for i in range(5):
        resp = client.post(
            "/api/applicant/submit",
            json={
                "privacy_agreed": True,
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "phone": _phone(100 + i),
            },
        )
        assert resp.status_code == 200, resp.text
    assert client.post(
        "/api/applicant/submit",
        json={
            "privacy_agreed": True,
            "first_name": "Juan",
            "last_name": "Dela Cruz",
            "phone": _phone(199),
        },
    ).status_code == 429


def test_disk_watermark_rejects_and_cleans(client, monkeypatch, upload_dirs, staff_headers):
    import app.routers.oss as oss_router

    monkeypatch.setattr(
        oss_router.shutil, "disk_usage", lambda _path: SimpleNamespace(free=0, total=0, used=0)
    )

    assert _upload(client).status_code == 503
    assert _upload(client, headers=staff_headers).status_code == 503
    assert list(upload_dirs.rglob("*")) == []


def test_normal_upload_counts_bytes(client, upload_dirs):
    resp = _upload(client, size=37)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["size"] == 37
    files = [p for p in upload_dirs.rglob("*") if p.is_file()]
    assert len(files) == 1
    assert files[0].stat().st_size == 37


def test_daily_quota_resets_next_day(client, monkeypatch, upload_dirs):
    monkeypatch.setattr(settings, "UPLOAD_ANON_DAILY_REQUESTS", 1)

    assert _upload(client).status_code == 200
    assert _upload(client).status_code == 429

    # 把计数日期改成昨天，模拟跨天
    key = "oss_upload:ip:testclient"
    day, count, used = ratelimit._daily[key]
    ratelimit._daily[key] = ("2000-01-01", count, used)
    assert day

    assert _upload(client).status_code == 200
