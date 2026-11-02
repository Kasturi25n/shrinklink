from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Click, User, utcnow
from app.routers.links import get_owned_link
from app.schemas import AnalyticsOut, CountItem, DayCount
from app.security import get_current_user

router = APIRouter(prefix="/api/links", tags=["analytics"])


def _top(db: Session, link_id: int, column, since, limit: int = 10) -> List[CountItem]:
    """Group clicks by one column, most frequent first. NULLs are reported as 'Unknown'."""
    rows = db.execute(
        select(column, func.count())
        .where(Click.link_id == link_id, Click.clicked_at >= since)
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [CountItem(label=value or "Unknown", count=count) for value, count in rows]


@router.get("/{code}/analytics", response_model=AnalyticsOut)
def link_analytics(
    code: str,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    link = get_owned_link(code, user, db)
    since = utcnow() - timedelta(days=days)

    total = db.scalar(
        select(func.count()).where(Click.link_id == link.id, Click.clicked_at >= since)
    )

    day = func.date(Click.clicked_at)
    by_day = db.execute(
        select(day, func.count())
        .where(Click.link_id == link.id, Click.clicked_at >= since)
        .group_by(day)
        .order_by(day)
    ).all()

    return AnalyticsOut(
        code=link.code,
        total_clicks=total or 0,
        clicks_by_day=[DayCount(date=str(d), count=c) for d, c in by_day],
        top_referrers=_top(db, link.id, Click.referrer, since),
        browsers=_top(db, link.id, Click.browser, since),
        devices=_top(db, link.id, Click.device, since),
        countries=_top(db, link.id, Click.country, since),
    )
