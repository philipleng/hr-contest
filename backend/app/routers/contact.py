"""联系与跟进 API：今日待跟进列表"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Applicant, ContactLog, Staff
from app.routers.applicant import get_current_staff
from app.schemas import ApiResponse, FollowUpItem
from app.utils.tz import day_range

router = APIRouter(prefix="/contact", tags=["contact"])


@router.get("/follow-ups", response_model=ApiResponse)
def follow_ups(
    db: Session = Depends(get_db),
    _: Staff = Depends(get_current_staff),
):
    """今日待跟进（含逾期）。

    只看每个候选人的最后一条联系记录：后续记录若把 next_follow_at 置空，
    说明已经不再需要跟进，旧的待办不应继续冒出来。
    """
    latest = (
        select(func.max(ContactLog.id).label("id"))
        .group_by(ContactLog.applicant_id)
        .subquery()
    )
    _, deadline = day_range()

    rows = db.execute(
        select(
            ContactLog,
            Applicant.first_name,
            Applicant.last_name,
            Applicant.phone,
            Staff.real_name,
        )
        .join(latest, latest.c.id == ContactLog.id)
        .join(Applicant, Applicant.id == ContactLog.applicant_id)
        .outerjoin(Staff, Staff.id == ContactLog.operator_id)
        .where(Applicant.deleted_at.is_(None))
        .where(ContactLog.next_follow_at.is_not(None))
        .where(ContactLog.next_follow_at < deadline)
        .order_by(ContactLog.next_follow_at.asc(), ContactLog.id.asc())
        .limit(200)
    ).all()

    items = [
        FollowUpItem(
            contact_id=log.id,
            applicant_id=log.applicant_id,
            applicant_name=f"{first_name} {last_name}",
            phone=phone,
            channel=log.channel,
            result=log.result,
            note=log.note,
            next_follow_at=log.next_follow_at,
            operator_name=real_name,
        ).model_dump(mode="json")
        for log, first_name, last_name, phone, real_name in rows
    ]
    return ApiResponse(data=items)
