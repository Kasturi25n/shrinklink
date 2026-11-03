from datetime import timedelta

from app.database import SessionLocal
from app.models import Click, Link, utcnow
from app.useragent import parse_browser, parse_device, referrer_host

CHROME_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def make_link(client, auth):
    r = client.post("/api/links", json={"url": "https://example.com"}, headers=auth)
    return r.json()["code"]


def click(client, code, ua, referer=None, country=None):
    headers = {"user-agent": ua}
    if referer:
        headers["referer"] = referer
    if country:
        headers["cf-ipcountry"] = country
    client.get(f"/{code}", headers=headers, follow_redirects=False)


def test_clicks_are_recorded_and_aggregated(client, auth):
    code = make_link(client, auth)
    click(client, code, CHROME_DESKTOP, "https://twitter.com/some/post?x=1", "IN")
    click(client, code, CHROME_DESKTOP, "https://twitter.com/other", "IN")
    click(client, code, SAFARI_IPHONE, "https://news.ycombinator.com/item?id=1", "US")
    click(client, code, SAFARI_IPHONE)  # direct visit: no referrer, no country

    data = client.get(f"/api/links/{code}/analytics", headers=auth).json()
    assert data["total_clicks"] == 4
    assert data["top_referrers"][0] == {"label": "twitter.com", "count": 2}
    assert {"label": "Unknown", "count": 1} in data["top_referrers"]
    assert {"label": "Chrome", "count": 2} in data["browsers"]
    assert {"label": "Safari", "count": 2} in data["browsers"]
    assert {"label": "Mobile", "count": 2} in data["devices"]
    assert {"label": "Desktop", "count": 2} in data["devices"]
    assert data["countries"][0] == {"label": "IN", "count": 2}
    assert data["clicks_by_day"] == [{"date": utcnow().date().isoformat(), "count": 4}]


def test_referrer_stores_host_only(client, auth):
    code = make_link(client, auth)
    click(client, code, CHROME_DESKTOP, "https://example.org/private/path?token=secret")
    with SessionLocal() as db:
        stored = db.query(Click).one().referrer
    assert stored == "example.org"


def test_days_window_excludes_old_clicks(client, auth):
    code = make_link(client, auth)
    click(client, code, CHROME_DESKTOP)
    with SessionLocal() as db:
        link = db.query(Link).filter(Link.code == code).one()
        db.add(Click(link_id=link.id, clicked_at=utcnow() - timedelta(days=60)))
        db.commit()

    assert client.get(f"/api/links/{code}/analytics?days=30", headers=auth).json()["total_clicks"] == 1
    assert client.get(f"/api/links/{code}/analytics?days=90", headers=auth).json()["total_clicks"] == 2


def test_analytics_empty_link(client, auth):
    code = make_link(client, auth)
    data = client.get(f"/api/links/{code}/analytics", headers=auth).json()
    assert data["total_clicks"] == 0
    assert data["clicks_by_day"] == []


def test_analytics_is_owner_only(client, auth):
    from tests.conftest import register_and_login

    code = make_link(client, auth)
    other = register_and_login(client, email="other@example.com")
    assert client.get(f"/api/links/{code}/analytics", headers=other).status_code == 404
    assert client.get(f"/api/links/{code}/analytics").status_code == 401


def test_deleting_link_removes_its_clicks(client, auth):
    code = make_link(client, auth)
    click(client, code, CHROME_DESKTOP)
    client.delete(f"/api/links/{code}", headers=auth)
    with SessionLocal() as db:
        assert db.query(Click).count() == 0


def test_user_agent_parsing():
    assert parse_browser(CHROME_DESKTOP) == "Chrome"
    assert parse_browser(SAFARI_IPHONE) == "Safari"
    assert parse_browser("Mozilla/5.0 Firefox/121.0") == "Firefox"
    assert parse_browser("Mozilla/5.0 Chrome/120 Safari/537 Edg/120") == "Edge"
    assert parse_browser("curl/8.0") == "Bot"
    assert parse_device(SAFARI_IPHONE) == "Mobile"
    assert parse_device(CHROME_DESKTOP) == "Desktop"
    assert parse_device("Mozilla/5.0 (iPad; CPU OS 17_0)") == "Tablet"
    assert referrer_host(None) is None
    assert referrer_host("") is None
    assert referrer_host("https://a.com/x?y=1") == "a.com"


def test_country_from_trusted_edge_header_only(client, auth, settings, monkeypatch):
    # Through Vercel, cf-ipcountry is Vercel's server location, so only the edge's
    # x-visitor-country counts; without the secret anyone could forge that header.
    monkeypatch.setattr(settings, "proxy_secret", "s3cret")
    code = make_link(client, auth)
    vercel = {"x-proxy-secret": "s3cret"}
    client.get(f"/{code}", headers={**vercel, "x-visitor-country": "in", "cf-ipcountry": "US"}, follow_redirects=False)
    client.get(f"/{code}", headers={**vercel, "cf-ipcountry": "US"}, follow_redirects=False)  # edge had no geo
    client.get(f"/{code}", headers={"x-visitor-country": "FR", "cf-ipcountry": "GB"}, follow_redirects=False)  # direct, forged
    client.get(f"/{code}", headers={"x-proxy-secret": "wrong", "x-visitor-country": "FR"}, follow_redirects=False)
    client.get(f"/{code}", headers={"cf-ipcountry": "XX"}, follow_redirects=False)  # unknown
    client.get(f"/{code}", headers={**vercel, "x-visitor-country": "<script>"}, follow_redirects=False)  # junk
    countries = client.get(f"/api/links/{code}/analytics", headers=auth).json()["countries"]
    assert sorted((c["label"], c["count"]) for c in countries) == [("GB", 1), ("IN", 1), ("Unknown", 4)]
