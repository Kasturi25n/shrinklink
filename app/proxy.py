"""Who sent this request? Answering that safely behind proxies.

Production path:  browser -> Vercel -> Cloudflare (Render's edge) -> Render's balancer -> app

Each proxy appends the address it received the connection from to X-Forwarded-For.
Only the entries appended by proxies we know about can be trusted; anything to their
left was written by whoever sent the request and can be forged. (The old code took the
leftmost entry, so a client could pick a fresh "IP" per request and dodge rate limits.)

Resolution order:
1. Vercel proves itself with a shared secret header, which vercel.json sets from an env
   var and which overwrites any value a visitor sends. Only then do we believe Vercel's
   view of the visitor: x-vercel-forwarded-for and x-vercel-ip-country.
2. Otherwise, count TRUSTED_PROXY_HOPS entries from the right of X-Forwarded-For.
   On Render that is 3: [..., client, cloudflare, render-balancer].
3. With neither configured (local dev, tests): the socket peer.
"""
import hmac
from typing import List, Optional

from fastapi import Request

from app.config import Settings

SECRET_HEADER = "x-proxy-secret"


def from_trusted_edge(request: Request, settings: Settings) -> bool:
    secret = settings.proxy_secret
    sent = request.headers.get(SECRET_HEADER)
    if not secret or not sent:
        return False
    return hmac.compare_digest(sent.encode(), secret.encode())


def _forwarded_chain(request: Request) -> List[str]:
    raw = request.headers.get("x-forwarded-for", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def client_ip(request: Request, settings: Settings) -> str:
    if from_trusted_edge(request, settings):
        ip = request.headers.get("x-vercel-forwarded-for", "").split(",")[0].strip()
        if ip:
            return ip

    hops = settings.trusted_proxy_hops
    chain = _forwarded_chain(request)
    if hops > 0 and chain:
        # A chain shorter than expected was written entirely by trusted proxies,
        # so its leftmost entry is still genuine.
        return chain[-hops] if len(chain) >= hops else chain[0]

    return request.client.host if request.client else "unknown"


def visitor_country(request: Request, settings: Settings) -> Optional[str]:
    """Two-letter country of the visitor, or None (e.g. when running locally).

    Through Vercel, Cloudflare at the origin sees Vercel's server, so cf-ipcountry would
    report Vercel's location; Vercel's own header is right, but only once the request
    is proven to come from Vercel. Cloudflare overwrites cf-ipcountry, so it can't be forged.
    """
    headers = ["cf-ipcountry"]
    if from_trusted_edge(request, settings):
        headers.insert(0, "x-vercel-ip-country")
    for header in headers:
        value = (request.headers.get(header) or "").strip().upper()
        # Two-letter ISO codes only; Cloudflare uses XX (unknown) and T1 (Tor).
        if len(value) == 2 and value.isalpha() and value != "XX":
            return value
    return None
