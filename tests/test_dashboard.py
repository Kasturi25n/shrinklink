from datetime import timedelta

from app.database import SessionLocal
from app.models import Link, utcnow
from tests.conftest import register_and_login

CHROME = "Mozilla/5.0 Chrome/120 Safari/537"


def create(client, auth, **body):
    body.setdefault("url", "https://example.com/page")
    return client.post("/api/links", json=body, headers=auth)


# ---------- the page itself ----------
def test_dashboard_is_served_with_a_locked_down_csp(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Link analytics" in r.text
    csp = r.headers["content-security-policy"]
    assert "connect-src 'self'" in csp and "default-src 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"


def test_root_redirects_to_dashboard(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/dashboard"


def test_dashboard_is_not_a_valid_alias(client, auth):
    # otherwise a user could claim the path the UI lives on
    assert create(client, auth, custom_alias="dashboard").status_code == 400


def test_page_uses_no_html_injection_sinks(client):
    # Link targets and referrers are attacker-controlled, so the page must build its DOM
    # with textContent / text nodes only. Strip comments first so prose can't trip this.
    import re

    html = client.get("/dashboard").text
    code = re.sub(r"/\*.*?\*/|(?<!:)//[^\n]*", "", html, flags=re.S)
    sinks = [r"\.innerHTML\s*\+?=", r"\.outerHTML\s*=", r"insertAdjacentHTML", r"document\.write", r"\beval\s*\(", r"new Function"]
    for pattern in sinks:
        assert not re.search(pattern, code), f"dashboard uses an HTML-injection sink: {pattern}"


# ---------- click counts on the links list ----------
def test_list_includes_all_time_click_counts(client, auth):
    busy = create(client, auth).json()["code"]
    quiet = create(client, auth).json()["code"]
    for _ in range(3):
        client.get(f"/{busy}", headers={"user-agent": CHROME}, follow_redirects=False)

    counts = {l["code"]: l["clicks"] for l in client.get("/api/links", headers=auth).json()}
    assert counts == {busy: 3, quiet: 0}
    assert client.get(f"/api/links/{busy}", headers=auth).json()["clicks"] == 3
    assert create(client, auth).json()["clicks"] == 0


def test_click_counts_are_per_owner(client, auth):
    code = create(client, auth).json()["code"]
    client.get(f"/{code}", follow_redirects=False)
    other = register_and_login(client, email="other@example.com")
    create(client, other)
    assert [l["clicks"] for l in client.get("/api/links", headers=other).json()] == [0]


# ---------- timezone-aware expiry (what a browser date picker sends) ----------
def test_timezone_aware_expiry_is_accepted_and_stored_as_utc(client, auth):
    future = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    r = create(client, auth, expires_at=future.isoformat() + "Z")
    assert r.status_code == 201
    assert r.json()["expires_at"] == future.isoformat()


def test_timezone_offset_is_converted_to_utc(client, auth):
    future = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    # the same instant written with a +05:30 offset
    local = (future + timedelta(hours=5, minutes=30)).isoformat() + "+05:30"
    r = create(client, auth, expires_at=local)
    assert r.status_code == 201
    assert r.json()["expires_at"] == future.isoformat()


def test_timezone_aware_past_expiry_is_rejected_not_a_500(client, auth):
    past = (utcnow() - timedelta(hours=1)).replace(microsecond=0)
    assert create(client, auth, expires_at=past.isoformat() + "Z").status_code == 400


def test_expiring_link_created_via_aware_timestamp_redirects_then_expires(client, auth):
    future = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    code = create(client, auth, expires_at=future.isoformat() + "Z").json()["code"]
    assert client.get(f"/{code}", follow_redirects=False).status_code == 302
    with SessionLocal() as db:
        db.query(Link).filter(Link.code == code).update({"expires_at": utcnow() - timedelta(seconds=1)})
        db.commit()
    from app.cache import get_cache

    get_cache().delete(f"link:{code}")
    assert client.get(f"/{code}", follow_redirects=False).status_code == 410
