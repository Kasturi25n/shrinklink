from datetime import timedelta

from app.models import utcnow
from tests.conftest import register_and_login


def create(client, auth, **body):
    body.setdefault("url", "https://example.com/some/long/path")
    return client.post("/api/links", json=body, headers=auth)


def test_create_link_generates_code(client, auth):
    r = create(client, auth)
    assert r.status_code == 201
    data = r.json()
    assert len(data["code"]) == 7
    assert data["short_url"].endswith("/" + data["code"])
    assert data["target_url"] == "https://example.com/some/long/path"


def test_custom_alias(client, auth):
    r = create(client, auth, custom_alias="my-link")
    assert r.status_code == 201
    assert r.json()["code"] == "my-link"


def test_duplicate_alias_conflicts(client, auth):
    assert create(client, auth, custom_alias="taken").status_code == 201
    assert create(client, auth, custom_alias="taken").status_code == 409


def test_invalid_and_reserved_aliases_rejected(client, auth):
    assert create(client, auth, custom_alias="has space").status_code == 400
    assert create(client, auth, custom_alias="api").status_code == 400
    assert create(client, auth, custom_alias="docs").status_code == 400


def test_invalid_url_rejected(client, auth):
    assert create(client, auth, url="not a url").status_code == 422
    assert create(client, auth, url="javascript:alert(1)").status_code == 422
    assert create(client, auth, url="ftp://example.com/file").status_code == 422


def test_cannot_shorten_own_domain(client, auth):
    assert create(client, auth, url="http://localhost:8000/abc").status_code == 400


def test_expiry_must_be_in_future(client, auth):
    past = (utcnow() - timedelta(hours=1)).isoformat()
    assert create(client, auth, expires_at=past).status_code == 400


def test_list_only_returns_own_links(client, auth):
    create(client, auth)
    create(client, auth)
    other = register_and_login(client, email="other@example.com")
    create(client, other)

    assert len(client.get("/api/links", headers=auth).json()) == 2
    assert len(client.get("/api/links", headers=other).json()) == 1


def test_cannot_read_or_delete_someone_elses_link(client, auth):
    code = create(client, auth).json()["code"]
    other = register_and_login(client, email="other@example.com")
    assert client.get(f"/api/links/{code}", headers=other).status_code == 404
    assert client.delete(f"/api/links/{code}", headers=other).status_code == 404
    assert client.get(f"/api/links/{code}", headers=auth).status_code == 200


def test_delete_link(client, auth):
    code = create(client, auth).json()["code"]
    assert client.delete(f"/api/links/{code}", headers=auth).status_code == 204
    assert client.get(f"/api/links/{code}", headers=auth).status_code == 404


def test_create_rate_limit(client, auth, settings, monkeypatch):
    monkeypatch.setattr(settings, "create_rate_limit", 3)
    statuses = [create(client, auth).status_code for _ in range(5)]
    assert statuses == [201, 201, 201, 429, 429]
