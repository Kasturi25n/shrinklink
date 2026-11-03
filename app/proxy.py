"""Who sent this request? Answering that safely behind proxies.

Production path:  browser -> Vercel -> Cloudflare (Render's edge) -> Render's balancer -> app

Each proxy appends the address it received the connection from to X-Forwarded-For.
Only the entries appended by proxies we know about can be trusted; anything to their
left was written by whoever sent the request and can be forged. (The old code took the
leftmost entry, so a client could pick a fresh "IP" per request and dodge rate limits.)

Resolution order:
1. Count TRUSTED_PROXY_HOPS entries from the right of X-Forwarded-For.
   On Render that is 3: [..., client, cloudflare, render-balancer].
2. If Vercel proves itself with the shared secret header (vercel.json sets it from an env
   var, overwriting any value a visitor sends), the visitor is the last `for=` of the
   standard Forwarded header, which Vercel writes. Production probes showed some Vercel
   edges pass a visitor's own X-Forwarded-For and x-vercel-forwarded-for through
   untouched, while Forwarded was correct in every probe, forged or not.
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


def _forwarded_for(request: Request) -> Optional[str]:
    """The `for=` of the last element of an RFC 7239 Forwarded header."""
    last = request.headers.get("forwarded", "").split(",")[-1]
    for pair in last.split(";"):
        key, _, value = pair.strip().partition("=")
        if key.lower() == "for":
            value = value.strip('"')
            if value.startswith("["):  # quoted IPv6, optionally with a port
                return value[1:].split("]")[0] or None
            if value.count(":") == 1:  # IPv4 with a port
                value = value.split(":")[0]
            return value or None
    return None


def client_ip(request: Request, settings: Settings) -> str:
    if from_trusted_edge(request, settings):
        ip = _forwarded_for(request)
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

    Through Vercel, Cloudflare at the origin sees Vercel's server, so cf-ipcountry is
    Vercel's location, not the visitor's. vercel.json copies Vercel's geolocation into
    x-visitor-country (and deletes any visitor-sent copy); that header is believed only
    from the trusted edge. Direct requests use cf-ipcountry, which Cloudflare overwrites.
    """
    header = "x-visitor-country" if from_trusted_edge(request, settings) else "cf-ipcountry"
    value = (request.headers.get(header) or "").strip().upper()
    # Two-letter ISO codes only; Cloudflare uses XX (unknown) and T1 (Tor).
    if len(value) == 2 and value.isalpha() and value != "XX":
        return value
    return None
