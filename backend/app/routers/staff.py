"""员工管理路由：增删改查、重置密码、停用/启用（仅 admin 可用）"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Staff
from app.routers.applicant import require_admin as _require_admin
from app.schemas import (
    ApiResponse,
    StaffCreateRequest,
    StaffListData,
    StaffOut,
    StaffPasswordResetRequest,
    StaffStatusUpdateRequest,
    StaffUpdateRequest,
)
from app.utils.security import hash_password

router = APIRouter(prefix="/staff", tags=["staff"])


def require_admin(current: Staff = Depends(_require_admin)):
    """校验当前用户必须是 admin（复用 applicant 中的实现）"""
    return current


def count_active_admins(db: Session, exclude_id: int | None = None) -> int:
    """统计启用状态的 admin 数量（exclude_id 用于模拟「这个人被降级/停用后」）"""
    stmt = select(func.count(Staff.id)).where(Staff.role == "admin", Staff.status == "active")
    if exclude_id is not None:
        stmt = stmt.where(Staff.id != exclude_id)
    return db.scalar(stmt) or 0


@router.get("/list", response_model=ApiResponse)
def staff_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    status_filter: str | None = Query(None, alias="status", pattern="^(active|disabled)$"),
    role_filter: str | None = Query(None, alias="role", pattern="^(admin|staff)$"),
    db: Session = Depends(get_db),
    _: Staff = Depends(_require_admin),
):
    """员工列表（仅管理员：普通员工不应拉取全公司账号名册）"""
    stmt = select(Staff)
    count_stmt = select(func.count(Staff.id))

    if keyword:
        stmt = stmt.where(
            (Staff.username.contains(keyword))
            | (Staff.real_name.contains(keyword))
        )
        count_stmt = count_stmt.where(
            (Staff.username.contains(keyword))
            | (Staff.real_name.contains(keyword))
        )
    if status_filter:
        stmt = stmt.where(Staff.status == status_filter)
        count_stmt = count_stmt.where(Staff.status == status_filter)
    if role_filter:
        stmt = stmt.where(Staff.role == role_filter)
        count_stmt = count_stmt.where(Staff.role == role_filter)

    total = db.scalar(count_stmt)
    items = db.scalars(
        stmt.order_by(Staff.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ApiResponse(data=StaffListData(
        total=total, page=page, page_size=page_size,
        items=[StaffOut.model_validate(i) for i in items],
    ))


@router.get("/{staff_id}", response_model=ApiResponse)
def staff_detail(
    staff_id: int,
    db: Session = Depends(get_db),
    _: Staff = Depends(_require_admin),
):
    staff = db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff not found.")
    return ApiResponse(data=StaffOut.model_validate(staff))


@router.post("", response_model=ApiResponse)
def staff_create(
    req: StaffCreateRequest,
    db: Session = Depends(get_db),
    _: Staff = Depends(require_admin),
):
    # 用户名查重
    existing = db.scalar(select(Staff).where(Staff.username == req.username))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Username {req.username} is already in use.")

    staff = Staff(
        username=req.username,
        password_hash=hash_password(req.password),
        real_name=req.real_name,
        role=req.role,
        status="active",
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return ApiResponse(data=StaffOut.model_validate(staff))


@router.patch("/{staff_id}", response_model=ApiResponse)
def staff_update(
    staff_id: int,
    req: StaffUpdateRequest,
    db: Session = Depends(get_db),
    _: Staff = Depends(require_admin),
):
    staff = db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff not found.")

    # 防自锁：不能把最后一个启用的 admin 降级为 staff，否则没人能进后台管理
    if req.role == "staff" and staff.role == "admin" and staff.status == "active":
        if count_active_admins(db, exclude_id=staff.id) == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "At least one active admin is required, so this role cannot be changed.",
            )

    if req.real_name is not None:
        staff.real_name = req.real_name
    if req.role is not None:
        staff.role = req.role

    db.commit()
    db.refresh(staff)
    return ApiResponse(data=StaffOut.model_validate(staff))


@router.patch("/{staff_id}/password", response_model=ApiResponse)
def staff_reset_password(
    staff_id: int,
    req: StaffPasswordResetRequest,
    db: Session = Depends(get_db),
    _: Staff = Depends(require_admin),
):
    staff = db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff not found.")

    staff.password_hash = hash_password(req.password)
    db.commit()
    return ApiResponse(data={"id": staff.id, "username": staff.username})


@router.patch("/{staff_id}/status", response_model=ApiResponse)
def staff_update_status(
    staff_id: int,
    req: StaffStatusUpdateRequest,
    db: Session = Depends(get_db),
    current: Staff = Depends(require_admin),
):
    staff = db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff not found.")

    if req.status == "disabled":
        # 防自锁：自己把自己停用后，当前 token 也就失去管理能力了。
        # 无需再校验「最后一个启用 admin」：能执行到这里的调用者本身必是启用 admin，
        # 且 staff.id != current.id（上面已拦截自停用），停用任何其他账号后至少还剩调用者本人。
        if staff.id == current.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "You cannot disable your own account. Please ask another admin.",
            )

    staff.status = req.status
    db.commit()
    db.refresh(staff)
    return ApiResponse(data=StaffOut.model_validate(staff))
