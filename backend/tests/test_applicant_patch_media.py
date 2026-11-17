"""申请人编辑接口（PATCH /api/applicant/{id}）的媒体 key 校验"""

from sqlalchemy import select

from app.models import Applicant, ResumeDocument
from app.utils.upload_session import new_upload_session


def _create_applicant(client, submit_payload, **overrides) -> int:
    resp = client.post("/api/applicant/submit", json=submit_payload(**overrides))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_patch_rejects_local_traversal(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)

    for bad_key in ("local/../secret.jpg", "local\\secret.jpg"):
        resp = client.patch(
            f"/api/applicant/{applicant_id}",
            headers=staff_headers,
            json={"photo_oss_key": bad_key},
        )
        assert resp.status_code == 400


def test_patch_rejects_hr_without_matching_session(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)

    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"photo_oss_key": "hr/abc/photo.jpg"},
    )
    assert resp.status_code == 400

    other_token, _ = new_upload_session()
    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"photo_oss_key": "hr/abc/photo.jpg", "upload_session_token": other_token},
    )
    assert resp.status_code == 400


def test_patch_rejects_hr_traversal_even_with_valid_session(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)
    token, prefix = new_upload_session()

    for bad_key in (f"{prefix}../other.jpg", f"{prefix}..\\other.jpg"):
        resp = client.patch(
            f"/api/applicant/{applicant_id}",
            headers=staff_headers,
            json={"video_oss_key": bad_key, "upload_session_token": token},
        )
        assert resp.status_code == 400


def test_patch_rejects_disallowed_prefix(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)

    for bad_key in ("resume/a.pdf", "/etc/passwd"):
        resp = client.patch(
            f"/api/applicant/{applicant_id}",
            headers=staff_headers,
            json={"photo_oss_key": bad_key},
        )
        assert resp.status_code == 400


def test_patch_accepts_valid_local_and_matching_hr_keys(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)

    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"photo_oss_key": "local/2026/11/15/p.jpg"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["photo_oss_key"] == "local/2026/11/15/p.jpg"

    token, prefix = new_upload_session()
    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={
            "photo_oss_key": f"{prefix}p.jpg",
            "video_oss_key": f"{prefix}v.mp4",
            "upload_session_token": token,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["photo_oss_key"] == f"{prefix}p.jpg"
    assert resp.json()["data"]["video_oss_key"] == f"{prefix}v.mp4"


def test_patch_accepts_clearing_media_and_unchanged_hr_key(client, staff_headers, submit_payload):
    token, prefix = new_upload_session()
    existing_hr_key = f"{prefix}old.jpg"
    applicant_id = _create_applicant(
        client,
        submit_payload,
        photo_oss_key=existing_hr_key,
        upload_session_token=token,
    )

    # 仅修改其他字段，不传 token
    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"target_job": "CSR"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["photo_oss_key"] == existing_hr_key

    # 原样回传已有的 hr/... key，不传 token 也应放行
    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"photo_oss_key": existing_hr_key, "target_job": "BPO"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["photo_oss_key"] == existing_hr_key
    assert resp.json()["data"]["target_job"] == "BPO"

    # 传 None 清空媒体
    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"photo_oss_key": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["photo_oss_key"] is None


def test_patch_rejects_token_only_without_updates(client, staff_headers, submit_payload):
    applicant_id = _create_applicant(client, submit_payload)
    token, _ = new_upload_session()

    resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={"upload_session_token": token},
    )
    assert resp.status_code == 400


def test_patch_resume_converges_to_resume_document_with_real_size(
    client, db_session, staff_headers, submit_payload, tmp_path, monkeypatch,
):
    """PATCH 简历只写 ResumeDocument（含真实 file_size），不写入废弃主表列，且同 key 不重复新增"""
    import app.routers.applicant as applicant_router

    monkeypatch.setattr(applicant_router, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    resume_file = tmp_path / "resume" / "2026" / "11" / "16" / "updated.pdf"
    resume_file.parent.mkdir(parents=True)
    resume_bytes = b"%PDF-1.4 updated resume payload"
    resume_file.write_bytes(resume_bytes)

    applicant_id = _create_applicant(client, submit_payload)

    # 非法 resume_oss_key 返回 400
    for bad_key in ("resume/../secret.pdf", "resume\\secret.pdf", "local/a.pdf", "resume/"):
        bad = client.patch(
            f"/api/applicant/{applicant_id}",
            headers=staff_headers,
            json={"resume_oss_key": bad_key},
        )
        assert bad.status_code == 400

    # 传入有效 resume_oss_key → 写入 ResumeDocument，不写 applicant.resume_oss_key
    patch_resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={
            "resume_oss_key": "resume/2026/11/16/updated.pdf",
            "resume_file_name": "Updated_CV.pdf",
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["data"]["resume_oss_key"] is None
    assert patch_resp.json()["data"]["resume_file_name"] is None

    db_session.expire_all()
    applicant = db_session.get(Applicant, applicant_id)
    assert applicant.resume_oss_key is None
    assert applicant.resume_file_name is None

    docs = db_session.scalars(
        select(ResumeDocument).where(ResumeDocument.applicant_id == applicant_id)
    ).all()
    assert len(docs) == 1
    assert docs[0].oss_key == "resume/2026/11/16/updated.pdf"
    assert docs[0].file_name == "Updated_CV.pdf"
    assert docs[0].file_ext == ".pdf"
    assert docs[0].file_size == len(resume_bytes)

    # 重复传入相同 resume_oss_key 不重复新增
    dup_resp = client.patch(
        f"/api/applicant/{applicant_id}",
        headers=staff_headers,
        json={
            "resume_oss_key": "resume/2026/11/16/updated.pdf",
            "resume_file_name": "Updated_CV.pdf",
        },
    )
    assert dup_resp.status_code == 200
    docs_after_dup = db_session.scalars(
        select(ResumeDocument).where(ResumeDocument.applicant_id == applicant_id)
    ).all()
    assert len(docs_after_dup) == 1

    # 详情读回与下载接口均能读取新简历
    detail = client.get(f"/api/applicant/{applicant_id}", headers=staff_headers)
    assert detail.status_code == 200
    resumes = detail.json()["data"]["resumes"]
    assert len(resumes) == 1
    assert resumes[0]["file_name"] == "Updated_CV.pdf"
    assert resumes[0]["file_size"] == len(resume_bytes)

    download = client.get(f"/api/applicant/{applicant_id}/resume", headers=staff_headers)
    assert download.status_code == 200
    assert download.content == resume_bytes
