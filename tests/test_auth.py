def test_register_and_login(client):
    r = client.post("/api/auth/register", json={"email": "Me@Example.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["email"] == "me@example.com"  # normalised to lowercase

    r = client.post("/api/auth/login", json={"email": "me@example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_duplicate_email_rejected(client):
    body = {"email": "dup@example.com", "password": "password123"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_and_unknown_user_look_identical(client):
    client.post("/api/auth/register", json={"email": "x@example.com", "password": "password123"})
    wrong = client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "who@example.com", "password": "password123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_protected_routes_require_token(client):
    assert client.get("/api/links").status_code == 401
    assert client.post("/api/links", json={"url": "https://example.com"}).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/links", headers=bad).status_code == 401
