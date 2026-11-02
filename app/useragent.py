"""Tiny user-agent classifier. Good enough for analytics buckets without a dependency."""
from typing import Optional
from urllib.parse import urlparse


def parse_browser(ua: str) -> str:
    ua = ua.lower()
    # Order matters: Edge and Chrome UAs both contain "chrome"; Chrome contains "safari".
    for needle, name in (
        ("edg/", "Edge"),
        ("opr/", "Opera"),
        ("firefox/", "Firefox"),
        ("chrome/", "Chrome"),
        ("safari/", "Safari"),
    ):
        if needle in ua:
            return name
    if any(bot in ua for bot in ("bot", "crawler", "spider", "curl", "python-requests", "httpx")):
        return "Bot"
    return "Other"


def parse_device(ua: str) -> str:
    ua = ua.lower()
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "Mobile"
    return "Desktop"


def referrer_host(referrer: Optional[str]) -> Optional[str]:
    """Store only the host (e.g. 'twitter.com'), never full URLs with query strings."""
    if not referrer:
        return None
    host = urlparse(referrer).hostname
    return host[:255] if host else None
