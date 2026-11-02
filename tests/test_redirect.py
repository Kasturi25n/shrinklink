from datetime import timedelta

from app.cache import get_cache
from app.database import SessionLocal
from app.models import Link, utcnow


def make_link(client, auth, **body):
    body.setdefault("url", "https://example.com/target")
    return client.post("/api/links", json=body, headers=auth).json()["code"]


def test_redirects_to_target(client, auth):
    code = make_link(client, auth)
    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/target"


def test_unknown_code_is_404(client):
    assert client.get("/nope123", follow_redirects=False).status_code == 404


def test_second_request_is_served_from_cache(client, auth):
    code = make_link(client, auth)
    assert get_cache().get(f"link:{code}") is None
    client.get(f"/{code}", follow_redirects=False)
    assert get_cache().get(f"link:{code}") is not None

    # Remove the row behind the cache's back: a cache hit must still redirect.
    with SessionLocal() as db:
        db.query(Link).filter(Link.code == code).update({"target_url": "https://changed.example"})
        db.commit()
    r = client.get(f"/{code}", follow_redirects=False)
    assert r.headers["location"] == "https://example.com/target"


def test_delete_invalidates_cache(client, auth):
    code = make_link(client, auth)
    client.get(f"/{code}", follow_redirects=False)  # warm the cache
    client.delete(f"/api/links/{code}", headers=auth)
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404


def test_expired_link_returns_410(client, auth):
    code = make_link(client, auth)
    client.get(f"/{code}", follow_redirects=False)  # warm the cache
    with SessionLocal() as db:
        db.query(Link).filter(Link.code == code).update(
            {"expires_at": utcnow() - timedelta(seconds=1)}
        )
        db.commit()
    # Cached entry still has the old (null) expiry, so drop it as the app would on TTL.
    get_cache().delete(f"link:{code}")
    assert client.get(f"/{code}", follow_redirects=False).status_code == 410


def test_expiry_enforced_even_on_cache_hit(client, auth):
    soon = (utcnow() + timedelta(seconds=30)).isoformat()
    code = make_link(client, auth, expires_at=soon)
    assert client.get(f"/{code}", follow_redirects=False).status_code == 302

    # Rewrite the cached entry to look expired: the check must run on cache hits too.
    import json

    entry = json.loads(get_cache().get(f"link:{code}"))
    entry["expires_at"] = (utcnow() - timedelta(seconds=1)).isoformat()
    get_cache().set(f"link:{code}", json.dumps(entry), 60)
    assert client.get(f"/{code}", follow_redirects=False).status_code == 410


def test_redirect_rate_limit(client, auth, settings, monkeypatch):
    monkeypatch.setattr(settings, "redirect_rate_limit", 2)
    code = make_link(client, auth)
    statuses = [client.get(f"/{code}", follow_redirects=False).status_code for _ in range(4)]
    assert statuses == [302, 302, 429, 429]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
