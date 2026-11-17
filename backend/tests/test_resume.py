"""简历私有下载用例：必须登录、路径穿越防护、响应头"""

from app.models import ResumeDocument

SUBMIT = "/api/applicant/submit"


def _create(client, submit_payload, **overrides) -> int:
    resp = client.post(SUBMIT, json=submit_payload(**overrides))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def test_resume_requires_login(client, submit_payload):
    """未登录不允许下载简历"""
    applicant_id = _create(client, submit_payload, resume_oss_key="resume/2026/11/11/abc.pdf")

    resp = client.get(f"/api/applicant/{applicant_id}/resume")

    assert resp.status_code == 401


def test_resume_missing(client, submit_payload, staff_headers):
    """没有简历的申请人返回 404"""
    applicant_id = _create(client, submit_payload)

    resp = client.get(f"/api/applicant/{applicant_id}/resume", headers=staff_headers)

    assert resp.status_code == 404


def test_resume_download(client, submit_payload, staff_headers, tmp_path, monkeypatch):
    """登录后可下载，且强制 attachment、不缓存"""
    import app.routers.applicant as applicant_router

    monkeypatch.setattr(applicant_router, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    target = tmp_path / "resume" / "2026" / "11" / "11" / "abc.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 test")

    applicant_id = _create(
        client,
        submit_payload,
        resume_oss_key="resume/2026/11/11/abc.pdf",
        resume_file_name="Juan_CV.pdf",
    )

    resp = client.get(f"/api/applicant/{applicant_id}/resume", headers=staff_headers)

    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 test"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "Juan_CV.pdf" in disposition
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_submit_and_patch_reject_invalid_resume_key(client, submit_payload, staff_headers):
    """提交与编辑接口直接拦截路径穿越及非 resume/ 前缀的简历 key（返回 400）"""
    bad_keys = (
        "resume/../../../etc/passwd",
        "resume\\..\\secret.pdf",
        "local/2026/11/11/abc.pdf",
        "resume/",
    )
    for idx, bad_key in enumerate(bad_keys):
        resp = client.post(
            SUBMIT,
            json=submit_payload(
                phone=f"0917810000{idx}",
                resume_oss_key=bad_key,
            ),
        )
        assert resp.status_code == 400, f"submit should reject {bad_key}"

    applicant_id = _create(client, submit_payload, phone="09178100099")
    for bad_key in bad_keys:
        resp = client.patch(
            f"/api/applicant/{applicant_id}",
            headers=staff_headers,
            json={"resume_oss_key": bad_key},
        )
        assert resp.status_code == 400, f"patch should reject {bad_key}"


def test_resume_rejects_path_traversal(
    client, db_session, submit_payload, staff_headers, tmp_path, monkeypatch,
):
    """纵深防御：即使库内存在带 ../ 的脏数据，下载接口仍拦截并返回 404"""
    import app.routers.applicant as applicant_router

    monkeypatch.setattr(applicant_router, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    (tmp_path / "resume").mkdir()

    applicant_id = _create(client, submit_payload)
    db_session.add(ResumeDocument(
        applicant_id=applicant_id,
        oss_key="resume/../../../etc/passwd",
        file_name="passwd",
        file_ext=".txt",
        file_size=0,
        extract_state=0,
    ))
    db_session.commit()

    resp = client.get(f"/api/applicant/{applicant_id}/resume", headers=staff_headers)

    assert resp.status_code == 404
