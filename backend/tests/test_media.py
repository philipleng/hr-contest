"""媒体读取鉴权用例：签发必须登录且 key 属于申请人、令牌防篡改/过期、路径穿越防护"""

from app.utils.media_token import sign_media_token
from app.utils.upload_session import new_upload_session

SUBMIT = "/api/applicant/submit"


def _create(client, submit_payload, **overrides) -> int:
    resp = client.post(SUBMIT, json=submit_payload(**overrides))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_media_url_requires_login(client, submit_payload):
    """未登录不能签发媒体地址"""
    applicant_id = _create(client, submit_payload, photo_oss_key="local/2026/11/15/p.jpg")

    resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": "local/2026/11/15/p.jpg"},
    )

    assert resp.status_code == 401


def test_media_url_rejects_unrelated_key(client, submit_payload, staff_headers):
    """只允许签发申请人名下 photo/video，其它 key 一律 404"""
    applicant_id = _create(client, submit_payload, photo_oss_key="local/2026/11/15/p.jpg")

    resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": "local/2026/11/15/other.jpg"},
        headers=staff_headers,
    )

    assert resp.status_code == 404


def test_local_media_roundtrip(client, submit_payload, staff_headers, tmp_path, monkeypatch):
    """local 对象：登录签发 → 签名 URL 直读，内容与响应头正确"""
    import app.routers.media as media_router

    monkeypatch.setattr(media_router, "UPLOAD_DIR", str(tmp_path))
    rel = "local/2026/11/15/photo.jpg"
    target = tmp_path / "local" / "2026" / "11" / "15" / "photo.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xd8 fake jpeg")

    applicant_id = _create(client, submit_payload, photo_oss_key=rel)
    resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": rel},
        headers=staff_headers,
    )

    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert url.startswith("/api/media/")

    media = client.get(url)
    assert media.status_code == 200
    assert media.content == b"\xff\xd8 fake jpeg"
    assert media.headers["x-content-type-options"] == "nosniff"
    assert "private" in media.headers["cache-control"]


def test_local_upload_submit_media_e2e_roundtrip(
    client, submit_payload, staff_headers, tmp_path, monkeypatch
):
    """端到端集成：本地上传 → 提交申请人 → 签发媒体 URL → 读取字节完全一致"""
    import app.routers.media as media_router
    import app.routers.oss as oss_router

    monkeypatch.setattr(oss_router, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(media_router, "UPLOAD_DIR", str(tmp_path))

    image_bytes = b"\xff\xd8\xff\xe0e2e-jpeg-payload\xff\xd9"
    upload_resp = client.post(
        "/api/oss/upload",
        files={"file": ("photo.jpg", image_bytes, "image/jpeg")},
        data={"kind": "media"},
    )
    assert upload_resp.status_code == 200, upload_resp.text
    key = upload_resp.json()["data"]["key"]
    assert key.startswith("local/")

    applicant_id = _create(client, submit_payload, photo_oss_key=key)
    url_resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": key},
        headers=staff_headers,
    )
    assert url_resp.status_code == 200, url_resp.text
    url = url_resp.json()["data"]["url"]
    assert url.startswith("/api/media/")

    media_resp = client.get(url)
    assert media_resp.status_code == 200
    assert media_resp.content == image_bytes


def test_local_seed_media_readable(client, submit_payload, staff_headers, tmp_path, monkeypatch):
    """local/seed/demo.jpg 演示素材路径兼容可读"""
    import app.routers.media as media_router

    monkeypatch.setattr(media_router, "UPLOAD_DIR", str(tmp_path))
    seed_bytes = b"\xff\xd8 demo seed image"
    seed_file = tmp_path / "local" / "seed" / "demo.jpg"
    seed_file.parent.mkdir(parents=True)
    seed_file.write_bytes(seed_bytes)

    rel = "local/seed/demo.jpg"
    applicant_id = _create(client, submit_payload, photo_oss_key=rel)
    url_resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": rel},
        headers=staff_headers,
    )
    assert url_resp.status_code == 200

    media_resp = client.get(url_resp.json()["data"]["url"])
    assert media_resp.status_code == 200
    assert media_resp.content == seed_bytes


def test_media_token_rejects_tamper_expiry_and_hr(client):
    """签名 URL 防篡改、防过期；hr/ 对象不经本地路径读取"""
    good = sign_media_token("local/2026/11/15/photo.jpg")
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert client.get(f"/api/media/{tampered}").status_code == 404

    expired = sign_media_token("local/2026/11/15/photo.jpg", ttl=-10)
    assert client.get(f"/api/media/{expired}").status_code == 404

    hr = sign_media_token("hr/2026/11/15/x.mp4")
    assert client.get(f"/api/media/{hr}").status_code == 404


def test_media_blocks_path_traversal(
    client, db_session, submit_payload, staff_headers, tmp_path, monkeypatch
):
    """穿越 key 即使拿到签名也不能逃出上传目录（提交侧已拦，读取侧仍需兜底）"""
    import app.routers.media as media_router
    from app.models import Applicant

    monkeypatch.setattr(media_router, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "local").mkdir(exist_ok=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")

    applicant_id = _create(client, submit_payload, photo_oss_key="local/2026/11/15/ok.jpg")
    row = db_session.get(Applicant, applicant_id)
    row.photo_oss_key = "local/../secret.txt"
    db_session.commit()

    evil = "local/../secret.txt"
    resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": evil},
        headers=staff_headers,
    )

    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert client.get(url).status_code == 404

    passwd_token = sign_media_token("local/../../etc/passwd")
    assert client.get(f"/api/media/{passwd_token}").status_code == 404


def test_hr_media_without_oss_returns_404(client, submit_payload, staff_headers):
    """OSS 未配置时，hr/ 对象签发返回 404（bucket 启用后改预签名 URL）"""
    token, prefix = new_upload_session()
    key = f"{prefix}x.mp4"
    applicant_id = _create(
        client, submit_payload, video_oss_key=key, upload_session_token=token
    )

    resp = client.get(
        f"/api/applicant/{applicant_id}/media-url",
        params={"key": key},
        headers=staff_headers,
    )

    assert resp.status_code == 404
