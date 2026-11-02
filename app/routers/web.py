"""Serves the single-page dashboard (plain HTML/CSS/JS, no build step)."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

DASHBOARD = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"

# The page only ever talks to its own origin and loads nothing external, so say so:
# even if an injection slipped through, the browser would refuse to send data elsewhere.
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


@router.get("/")
def root():
    return RedirectResponse("/dashboard", status_code=307)


@router.get("/dashboard")
def dashboard():
    return FileResponse(
        DASHBOARD,
        media_type="text/html",
        headers={"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff"},
    )
