"""员工登录 / JWT 签发"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Staff
from app.schemas import ApiResponse, LoginData, LoginRequest, StaffInfo
from app.utils.ratelimit import rate_limit
from app.utils.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# 与 StaffCreateRequest / 员工列表筛选的枚举保持一致；未知角色不得签发 token
ALLOWED_ROLES = {"admin", "staff"}


@router.post("/login", response_model=ApiResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # 同一 IP 每分钟最多 10 次登录尝试，防密码爆破
    rate_limit(request, "auth_login", max_times=10, window=60)

    staff = db.scalar(select(Staff).where(Staff.username == data.username))
    if not staff or not verify_password(data.password, staff.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong username or password.",
        )
    if staff.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )
    if staff.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account role is not allowed to sign in.",
        )

    token = create_access_token({
        "sub": str(staff.id),
        "username": staff.username,
        "role": staff.role,
    })

    return ApiResponse(data=LoginData(
        token=token,
        staff=StaffInfo(
            id=staff.id,
            username=staff.username,
            real_name=staff.real_name,
            role=staff.role,
        ),
    ))
