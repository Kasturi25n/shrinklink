from typing import List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Link, User, utcnow
from app.rate_limit import limit_creates
from app.schemas import LinkCreate, LinkOut
from app.security import get_current_user
from app.shortcode import generate_code, is_valid_alias

router = APIRouter(prefix="/api/links", tags=["links"])

MAX_CODE_ATTEMPTS = 5


def to_out(link: Link, settings: Settings) -> LinkOut:
    return LinkOut(
        code=link.code,
        short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
        target_url=link.target_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        is_active=link.is_active,
    )


def get_owned_link(code: str, user: User, db: Session) -> Link:
    link = db.scalar(select(Link).where(Link.code == code))
    # 404 (not 403) for other people's links so codes can't be probed.
    if link is None or link.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link


@router.post(
    "",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_creates)],
)
def create_link(
    body: LinkCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    target = str(body.url)

    # Refuse links that point back at ourselves (redirect loops / open-redirect chains).
    if urlparse(target).hostname == urlparse(settings.base_url).hostname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot shorten a link to this service")

    if body.expires_at is not None and body.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expires_at must be in the future")

    if body.custom_alias is not None:
        if not is_valid_alias(body.custom_alias):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Alias must be 3-32 chars (letters, digits, - or _) and not a reserved word",
            )
        link = Link(
            code=body.custom_alias,
            target_url=target,
            owner_id=user.id,
            expires_at=body.expires_at,
        )
        db.add(link)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Alias already taken")
        return to_out(link, settings)

    # Random code: retry on the (rare) collision. The UNIQUE constraint is the real guard.
    for _ in range(MAX_CODE_ATTEMPTS):
        link = Link(
            code=generate_code(settings.short_code_length),
            target_url=target,
            owner_id=user.id,
            expires_at=body.expires_at,
        )
        db.add(link)
        try:
            db.commit()
            return to_out(link, settings)
        except IntegrityError:
            db.rollback()
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not allocate a short code")


@router.get("", response_model=List[LinkOut])
def list_links(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    rows = db.scalars(
        select(Link)
        .where(Link.owner_id == user.id)
        .order_by(Link.created_at.desc(), Link.id.desc())
        .limit(limit)
        .offset(max(0, offset))
    )
    return [to_out(link, settings) for link in rows]


@router.get("/{code}", response_model=LinkOut)
def get_link(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return to_out(get_owned_link(code, user, db), settings)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(
    code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
):
    link = get_owned_link(code, user, db)
    db.delete(link)
    db.commit()
    cache.delete(f"link:{code}")  # otherwise the cached redirect would live on
    return Response(status_code=status.HTTP_204_NO_CONTENT)
