"""人才池 v3 用例：提交单写简历、来源表、归一化字段、详情多简历"""

from datetime import timedelta

from sqlalchemy import select

from app.models import Applicant, CandidateSource, ResumeDocument
from app.utils.tz import now_local

SUBMIT = "/api/applicant/submit"


def test_submit_writes_resume_document_and_source(client, db_session, submit_payload):
    """提交不再写旧列，改落 resume_document + candidate_source，并写归一化手机号"""
    resp = client.post(SUBMIT, json=submit_payload(
        phone="+63 917 555 0101",
        resume_oss_key="resume/2026/11/13/cv.pdf",
        resume_file_name="Juan_CV.pdf",
    ))

    assert resp.status_code == 200, resp.text
    applicant_id = resp.json()["data"]["applicant_id"]

    applicant = db_session.get(Applicant, applicant_id)
    assert applicant.resume_oss_key is None
    assert applicant.resume_file_name is None
    assert applicant.phone == "09175550101"
    assert applicant.phone_normalized == "09175550101"

    docs = db_session.scalars(
        select(ResumeDocument).where(ResumeDocument.applicant_id == applicant_id)
    ).all()
    assert len(docs) == 1
    assert docs[0].file_name == "Juan_CV.pdf"
    assert docs[0].file_ext == ".pdf"
    assert docs[0].extract_state == 0

    sources = db_session.scalars(
        select(CandidateSource).where(CandidateSource.applicant_id == applicant_id)
    ).all()
    assert len(sources) == 1
    assert sources[0].platform == "self"


def test_staff_submit_marks_source_staff(client, db_session, submit_payload, staff_headers):
    """扫楼代录：来源表记 staff，主档 source_type 同步"""
    resp = client.post(SUBMIT, json=submit_payload(), headers=staff_headers)

    assert resp.status_code == 200, resp.text
    applicant_id = resp.json()["data"]["applicant_id"]

    applicant = db_session.get(Applicant, applicant_id)
    assert applicant.source_type == "staff"

    sources = db_session.scalars(
        select(CandidateSource).where(CandidateSource.applicant_id == applicant_id)
    ).all()
    assert [source.platform for source in sources] == ["staff"]


def test_detail_returns_multiple_resumes_and_sources(
    client, db_session, submit_payload, staff_headers,
):
    """详情返回多份简历（新的在前）与来源列表"""
    resp = client.post(SUBMIT, json=submit_payload(
        resume_oss_key="resume/2026/11/13/old.pdf",
        resume_file_name="Old_CV.pdf",
    ))
    assert resp.status_code == 200, resp.text
    applicant_id = resp.json()["data"]["applicant_id"]

    db_session.add(ResumeDocument(
        applicant_id=applicant_id,
        oss_key="resume/2026/11/14/new.pdf",
        file_name="New_CV.pdf",
        file_ext=".pdf",
        file_size=1,
        extract_state=1,
        created_at=now_local() + timedelta(minutes=1),
        updated_at=now_local() + timedelta(minutes=1),
    ))
    db_session.add(CandidateSource(
        applicant_id=applicant_id,
        platform="facebook",
        platform_profile_id=f"FB{applicant_id:06d}",
    ))
    db_session.commit()

    detail = client.get(f"/api/applicant/{applicant_id}", headers=staff_headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]

    assert next(doc["file_name"] for doc in data["resumes"]) == "New_CV.pdf"
    assert len(data["resumes"]) == 2
    assert len(data["sources"]) == 2


def test_download_uses_latest_resume(
    client, db_session, submit_payload, staff_headers, tmp_path, monkeypatch,
):
    """下载接口取 resume_document 中最新一条，不再读 applicant.resume_oss_key"""
    import app.routers.applicant as applicant_router

    monkeypatch.setattr(applicant_router, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    old_file = tmp_path / "resume" / "seed" / "old.pdf"
    new_file = tmp_path / "resume" / "seed" / "new.pdf"
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"%PDF old")
    new_file.write_bytes(b"%PDF new")

    resp = client.post(SUBMIT, json=submit_payload())
    assert resp.status_code == 200, resp.text
    applicant_id = resp.json()["data"]["applicant_id"]

    now = now_local()
    db_session.add_all([
        ResumeDocument(
            applicant_id=applicant_id, oss_key="resume/seed/old.pdf",
            file_name="old.pdf", file_ext=".pdf", file_size=8,
            extract_state=1, created_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1),
        ),
        ResumeDocument(
            applicant_id=applicant_id, oss_key="resume/seed/new.pdf",
            file_name="new.pdf", file_ext=".pdf", file_size=8,
            extract_state=1, created_at=now, updated_at=now,
        ),
    ])
    db_session.commit()

    download = client.get(f"/api/applicant/{applicant_id}/resume", headers=staff_headers)

    assert download.status_code == 200
    assert download.content == b"%PDF new"
    assert "new.pdf" in download.headers["content-disposition"]


def test_submit_records_real_resume_file_size(
    client, db_session, submit_payload, tmp_path, monkeypatch,
):
    """提交带本地私有简历文件时，ResumeDocument.file_size 写入真实字节数"""
    import app.routers.applicant as applicant_router

    monkeypatch.setattr(applicant_router, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    resume_file = tmp_path / "resume" / "2026" / "11" / "16" / "real_cv.pdf"
    resume_file.parent.mkdir(parents=True)
    payload_bytes = b"%PDF-1.4 real content 12345"
    resume_file.write_bytes(payload_bytes)

    resp = client.post(SUBMIT, json=submit_payload(
        phone="09175550999",
        resume_oss_key="resume/2026/11/16/real_cv.pdf",
        resume_file_name="Real_CV.pdf",
    ))
    assert resp.status_code == 200, resp.text
    applicant_id = resp.json()["data"]["applicant_id"]

    doc = db_session.scalar(
        select(ResumeDocument).where(ResumeDocument.applicant_id == applicant_id)
    )
    assert doc is not None
    assert doc.file_size == len(payload_bytes)
