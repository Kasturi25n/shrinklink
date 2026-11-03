"""Fixed-window rate limiting, keyed by client IP (see app/proxy.py) and a bucket name.

Fixed window is simple and cheap (one INCR per request). The known trade-off is
bursts at window boundaries (up to 2x the limit across the edge); a sliding
window or token bucket fixes that at the cost of more state.
"""
import logging

from fastapi import Depends, HTTPException, Request, status

from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.proxy import client_ip, from_trusted_edge

log = logging.getLogger("uvicorn.error")
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "x-vercel-forwarded-for", "cf-connecting-ip", "true-client-ip", "forwarded", "x-vercel-ip-country", "cf-ipcountry")


def _limiter(bucket: str, limit_attr: str):
    def dependency(
        request: Request,
        cache: Cache = Depends(get_cache),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if settings.log_proxy_headers:
            seen = {h: request.headers[h] for h in _PROXY_HEADERS if h in request.headers}
            log.info(
                "proxy headers peer=%s secret_sent=%s trusted_edge=%s resolved=%s %s",
                request.client.host if request.client else None,
                "x-proxy-secret" in request.headers,
                from_trusted_edge(request, settings),
                client_ip(request, settings),
                seen,
            )
        limit = getattr(settings, limit_attr)
        window = settings.rate_limit_window_seconds
        count = cache.incr(f"rl:{bucket}:{client_ip(request, settings)}", window)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(window)},
            )

    return dependency


limit_redirects = _limiter("redirect", "redirect_rate_limit")
limit_creates = _limiter("create", "create_rate_limit")
