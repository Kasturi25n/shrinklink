"""The hot path: GET /{code} -> 302 to the target.

Flow:  cache hit?  -> redirect immediately
       cache miss  -> one indexed DB lookup, populate cache, redirect
Click recording happens in a background task *after* the response is sent, so
analytics writes never add latency to the redirect.
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.database import SessionLocal, get_db
from app.models import Click, Link, utcnow
from app.rate_limit import limit_redirects
from app.useragent import parse_browser, parse_device, referrer_host

router = APIRouter(tags=["redirect"])


def record_click(
    link_id: int,
    referrer: Optional[str],
    user_agent: str,
    country: Optional[str],
) -> None:
    # Background tasks run after the request's DB session is closed, so open a fresh one.
    with SessionLocal() as db:
        db.add(
            Click(
                link_id=link_id,
                referrer=referrer_host(referrer),
                browser=parse_browser(user_agent),
                device=parse_device(user_agent),
                country=country,
            )
        )
        db.commit()


@router.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@router.get("/{code}", dependencies=[Depends(limit_redirects)], include_in_schema=False)
def redirect(
    code: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
):
    key = f"link:{code}"
    cached = cache.get(key)

    if cached is not None:
        data = json.loads(cached)
    else:
        link = db.scalar(select(Link).where(Link.code == code))
        if link is None or not link.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Short link not found")
        data = {
            "id": link.id,
            "url": link.target_url,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        }
        # Never cache longer than the link itself lives.
        ttl = settings.cache_ttl_seconds
        if link.expires_at is not None:
            ttl = min(ttl, max(1, int((link.expires_at - utcnow()).total_seconds())))
        cache.set(key, json.dumps(data), ttl)

    # Checked on every request, even cache hits, so expiry is exact.
    if data["expires_at"] and datetime.fromisoformat(data["expires_at"]) <= utcnow():
        raise HTTPException(status.HTTP_410_GONE, "This link has expired")

    background.add_task(
        record_click,
        data["id"],
        request.headers.get("referer"),
        request.headers.get("user-agent", ""),
        # Set by CDNs/proxies such as Cloudflare; absent when running locally.
        request.headers.get("cf-ipcountry"),
    )
    # 302, not 301: browsers cache 301s forever, which would hide repeat clicks from analytics.
    return RedirectResponse(data["url"], status_code=status.HTTP_302_FOUND)
