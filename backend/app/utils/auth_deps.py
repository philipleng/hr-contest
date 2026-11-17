"""共享鉴权依赖

从 applicant.py 迁出，供 applicant / oss 等路由共用，避免路由之间反向导入。
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Staff
from app.utils.security import decode_access_token


def get_optional_staff(
    request: Request,
    db: Session = Depends(get_db),
) -> Staff | None:
    """可选鉴权（用于免登录的提交/上传接口）

    - 没有 Authorization 头 → 返回 None，按匿名处理
    - 有头但 token 非法/过期/员工已停用 → 直接 401，不做静默降级
      （静默降级会让攻击者用一个坏 token 绕过代录校验）
    """
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None

    if not auth.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authorization header must be in the form Bearer <token>",
        )

    payload = decode_access_token(auth.removeprefix("Bearer "))
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")

    try:
        staff_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload.")

    staff = db.get(Staff, staff_id)
    if not staff or staff.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Staff not found or disabled.")
    return staff


def get_current_staff(staff: Staff | None = Depends(get_optional_staff)) -> Staff:
    """必须登录"""
    if staff is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Authorization header.")
    return staff


def require_admin(staff: Staff = Depends(get_current_staff)) -> Staff:
    """必须是管理员"""
    if staff.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action.")
    return staff
