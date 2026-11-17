"""提交接口的媒体 key 校验：hr/ 必须匹配上传会话，local/ 拒绝路径穿越"""

from app.utils.upload_session import new_upload_session

SUBMIT = "/api/applicant/submit"


def _submit(client, submit_payload, **overrides):
    return client.post(SUBMIT, json=submit_payload(**overrides))


def test_submit_rejects_hr_without_session(client, submit_payload):
    resp = _submit(client, submit_payload, photo_oss_key="hr/abc/photo.jpg")

    assert resp.status_code == 400


def test_submit_rejects_hr_with_wrong_prefix(client, submit_payload):
    other_token, _ = new_upload_session()
    resp = _submit(
        client,
        submit_payload,
        photo_oss_key="hr/abc/photo.jpg",
        upload_session_token=other_token,
    )

    assert resp.status_code == 400


def test_submit_accepts_hr_with_matching_session(client, submit_payload):
    token, prefix = new_upload_session()
    resp = _submit(
        client,
        submit_payload,
        photo_oss_key=f"{prefix}photo.jpg",
        video_oss_key=f"{prefix}video.mp4",
        upload_session_token=token,
    )

    assert resp.status_code == 200, resp.text


def test_submit_rejects_traversal_local_key(client, submit_payload):
    resp = _submit(client, submit_payload, photo_oss_key="local/../secret.jpg")

    assert resp.status_code == 400


def test_submit_rejects_traversal_hr_key_even_with_valid_session(client, submit_payload):
    token, prefix = new_upload_session()
    resp = _submit(
        client,
        submit_payload,
        photo_oss_key=f"{prefix}../other/photo.jpg",
        upload_session_token=token,
    )

    assert resp.status_code == 400


def test_submit_accepts_valid_local_key(client, submit_payload):
    resp = _submit(client, submit_payload, photo_oss_key="local/2026/11/15/photo.jpg")

    assert resp.status_code == 200, resp.text


def test_submit_rejects_invalid_resume_oss_key(client, submit_payload):
    for idx, bad_key in enumerate((
        "resume/../../../etc/passwd",
        "resume\\2026\\cv.pdf",
        "local/2026/11/15/cv.pdf",
        "hr/abc/cv.pdf",
        "resume/",
    )):
        resp = _submit(
            client,
            submit_payload,
            phone=f"0917820000{idx}",
            resume_oss_key=bad_key,
        )
        assert resp.status_code == 400, f"expected 400 for {bad_key}"


def test_submit_accepts_valid_resume_oss_key(client, submit_payload):
    ok = _submit(
        client,
        submit_payload,
        phone="09178200099",
        resume_oss_key="resume/2026/11/16/cv.pdf",
    )
    assert ok.status_code == 200, ok.text
