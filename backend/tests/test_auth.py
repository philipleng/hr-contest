"""AUTH 组 P0 用例：登录、JWT 鉴权、员工管理权限边界

编号对应「最小测试集 · AUTH 组」。断言一律基于现有实现；
与预期不一致的行为在用例 docstring 中标注「锁定现状」。
"""

from datetime import datetime, timezone

import jwt

from app.config import settings
from app.utils.security import create_access_token

APPLICANT_LIST = "/api/applicant/list"
STAFF_LIST = "/api/staff/list"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_01_login_success(client, make_staff, staff_password):
    """AUTH-01 正确账号登录：200 + token + role=admin + 无密码字段"""
    admin = make_staff(username="admin01", role="admin", real_name="Admin One")

    resp = client.post("/api/auth/login", json={"username": "admin01", "password": staff_password})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    data = body["data"]
    assert isinstance(data["token"], str) and data["token"]
    assert data["token"].count(".") == 2  # JWT 三段结构
    assert data["staff"] == {
        "id": admin.id,
        "username": "admin01",
        "real_name": "Admin One",
        "role": "admin",
    }
    assert "password" not in resp.text.lower()


def test_auth_02_wrong_password(client, make_staff):
    """AUTH-02 错误密码：401，响应体不含 token"""
    make_staff(username="staff02")

    resp = client.post("/api/auth/login", json={"username": "staff02", "password": "wrong-pass"})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Wrong username or password."}
    assert "token" not in resp.text


def test_auth_03_disabled_login(client, make_staff, staff_password):
    """AUTH-03 停用账号登录：403（密码正确时才暴露停用状态）"""
    make_staff(username="staff03", status="disabled")

    resp = client.post("/api/auth/login", json={"username": "staff03", "password": staff_password})

    assert resp.status_code == 403
    assert resp.json() == {"detail": "This account is disabled."}
    assert "token" not in resp.text


def test_auth_04_no_token(client):
    """AUTH-04 无 token 访问受保护接口：401"""
    resp = client.get(APPLICANT_LIST)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Authorization header."}


def test_auth_05_tampered_token(client, make_staff, make_token):
    """AUTH-05 篡改签名：401"""
    admin = make_staff(username="admin05", role="admin")
    head, payload, signature = make_token(admin).split(".")
    flipped = "A" if signature[-1] != "A" else "B"
    tampered = f"{head}.{payload}.{signature[:-1]}{flipped}"

    resp = client.get(APPLICANT_LIST, headers=_bearer(tampered))

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired token."}


def test_auth_06_expired_token(client, make_staff, monkeypatch):
    """AUTH-06 过期 token（create_access_token 签发）：401"""
    admin = make_staff(username="admin06", role="admin")

    monkeypatch.setattr(settings, "JWT_EXPIRE_HOURS", -1)
    token = create_access_token({
        "sub": str(admin.id),
        "username": admin.username,
        "role": admin.role,
    })
    claims = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    assert claims["exp"] < datetime.now(timezone.utc).timestamp()

    resp = client.get(APPLICANT_LIST, headers=_bearer(token))

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired token."}
    # 过期只影响本次请求，账号本身仍启用
    assert admin.status == "active"


def test_auth_07_disabled_after_token_issued(client, make_staff, make_auth_headers, db_session):
    """AUTH-07 员工被停用后旧 token 立即失效：401（每次请求查库校验 status）"""
    staff = make_staff(username="staff07")
    headers = make_auth_headers(staff)

    staff.status = "disabled"
    db_session.commit()

    resp = client.get(APPLICANT_LIST, headers=headers)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Staff not found or disabled."}
    db_session.refresh(staff)
    assert staff.status == "disabled"


def test_auth_08_staff_cannot_list_staff(client, make_staff, make_auth_headers):
    """AUTH-08 staff 访问员工列表：403"""
    staff = make_staff(username="staff08")

    resp = client.get(STAFF_LIST, headers=make_auth_headers(staff))

    assert resp.status_code == 403
    assert resp.json() == {"detail": "You do not have permission for this action."}


def test_auth_09_staff_cannot_get_staff_detail(client, make_staff, make_auth_headers):
    """AUTH-09 staff 访问员工详情：403（鉴权在查库之前）"""
    admin = make_staff(username="admin09", role="admin")
    staff = make_staff(username="staff09")

    resp = client.get(f"/api/staff/{admin.id}", headers=make_auth_headers(staff))

    assert resp.status_code == 403
    assert resp.json() == {"detail": "You do not have permission for this action."}


def test_auth_10_admin_lists_staff_without_secrets(client, make_staff, make_auth_headers):
    """AUTH-10 admin 访问员工列表：200，响应不含 password_hash"""
    admin = make_staff(username="admin10", role="admin")
    make_staff(username="staff10")

    resp = client.get(STAFF_LIST, headers=make_auth_headers(admin))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert {item["username"] for item in data["items"]} == {"admin10", "staff10"}
    expected_keys = {"id", "username", "real_name", "role", "status", "created_at", "updated_at"}
    for item in data["items"]:
        assert set(item) == expected_keys
    assert "password_hash" not in resp.text
    assert "password" not in resp.text.lower()


def test_auth_11_admin_cannot_disable_self(
    client, make_staff, make_auth_headers, db_session,
):
    """AUTH-11 admin 停用自己：400，DB 状态不变"""
    admin = make_staff(username="admin11", role="admin")

    resp = client.patch(
        f"/api/staff/{admin.id}/status",
        json={"status": "disabled"},
        headers=make_auth_headers(admin),
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "You cannot disable your own account. Please ask another admin."}
    db_session.refresh(admin)
    assert admin.status == "active"


def test_auth_12_last_active_admin_guarded(
    client, make_staff, make_auth_headers, db_session,
):
    """AUTH-12 停用或降级最后一个启用 admin：400，DB 不变

    单管理员场景下「停用」由自停用守卫拦截（400）；
    staff_update_status 中「最后一个启用 admin 不可停用」的不可达分支已删除；
    降级路径仍会命中最后管理员守卫。
    """
    admin = make_staff(username="admin12", role="admin")
    headers = make_auth_headers(admin)

    # 降级：命中「至少保留一个启用 admin」守卫
    resp = client.patch(f"/api/staff/{admin.id}", json={"role": "staff"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "At least one active admin is required, so this role cannot be changed."
    }
    db_session.refresh(admin)
    assert admin.role == "admin"

    # 停用：单管理员时先命中自停用守卫
    resp = client.patch(
        f"/api/staff/{admin.id}/status", json={"status": "disabled"}, headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "You cannot disable your own account. Please ask another admin."
    }
    db_session.refresh(admin)
    assert admin.status == "active"
    assert admin.role == "admin"


def test_auth_13_unknown_role_rejected(client, make_staff, staff_password, db_session):
    """AUTH-13 未知角色登录：403，不签发 token；合法角色保持可用"""
    intern = make_staff(username="intern13", role="intern")

    resp = client.post(
        "/api/auth/login", json={"username": "intern13", "password": staff_password},
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "This account role is not allowed to sign in."}
    assert "token" not in resp.text
    db_session.refresh(intern)
    assert intern.role == "intern"
    assert intern.status == "active"

    # 合法角色（staff）登录行为不变
    make_staff(username="staff13")
    ok = client.post(
        "/api/auth/login", json={"username": "staff13", "password": staff_password},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["staff"]["role"] == "staff"


def test_auth_14_staff_list_filters_by_status_and_role(
    client, make_staff, make_auth_headers,
):
    """P1-A 员工列表支持 ?status= 与 ?role= 参数别名过滤"""
    admin = make_staff(username="admin14", role="admin", status="active")
    make_staff(username="staff14_active", role="staff", status="active")
    make_staff(username="staff14_disabled", role="staff", status="disabled")
    make_staff(username="admin14_disabled", role="admin", status="disabled")
    headers = make_auth_headers(admin)

    disabled_resp = client.get(STAFF_LIST, params={"status": "disabled"}, headers=headers)
    assert disabled_resp.status_code == 200
    assert {i["username"] for i in disabled_resp.json()["data"]["items"]} == {
        "staff14_disabled",
        "admin14_disabled",
    }

    admin_resp = client.get(STAFF_LIST, params={"role": "admin"}, headers=headers)
    assert admin_resp.status_code == 200
    assert {i["username"] for i in admin_resp.json()["data"]["items"]} == {
        "admin14",
        "admin14_disabled",
    }

    combined_resp = client.get(
        STAFF_LIST, params={"status": "active", "role": "staff"}, headers=headers,
    )
    assert combined_resp.status_code == 200
    assert [i["username"] for i in combined_resp.json()["data"]["items"]] == ["staff14_active"]


def test_auth_15_staff_password_min_length_8(
    client, make_staff, make_auth_headers,
):
    """P0-C 创建员工与重置密码要求至少 8 位（<8 返回 422，>=8 成功且可登录）"""
    admin = make_staff(username="admin15", role="admin")
    headers = make_auth_headers(admin)

    # 创建员工：<8 位拒绝
    short_create = client.post(
        "/api/staff",
        json={
            "username": "newstaff15",
            "password": "1234567",
            "real_name": "New Staff",
            "role": "staff",
        },
        headers=headers,
    )
    assert short_create.status_code == 422

    # 创建员工：>=8 位成功并可登录
    ok_create = client.post(
        "/api/staff",
        json={
            "username": "newstaff15",
            "password": "12345678",
            "real_name": "New Staff",
            "role": "staff",
        },
        headers=headers,
    )
    assert ok_create.status_code == 200
    staff_id = ok_create.json()["data"]["id"]

    login_ok = client.post(
        "/api/auth/login", json={"username": "newstaff15", "password": "12345678"},
    )
    assert login_ok.status_code == 200

    # 重置密码：<8 位拒绝
    short_reset = client.patch(
        f"/api/staff/{staff_id}/password",
        json={"password": "abcdefg"},
        headers=headers,
    )
    assert short_reset.status_code == 422

    # 重置密码：>=8 位成功且新密码可登录
    ok_reset = client.patch(
        f"/api/staff/{staff_id}/password",
        json={"password": "abcd1234"},
        headers=headers,
    )
    assert ok_reset.status_code == 200

    login_new = client.post(
        "/api/auth/login", json={"username": "newstaff15", "password": "abcd1234"},
    )
    assert login_new.status_code == 200
