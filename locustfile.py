"""Load test. Run the API with the rate limits raised, then start Locust:

    REDIRECT_RATE_LIMIT=10000000 CREATE_RATE_LIMIT=10000000 \
        uvicorn app.main:app --port 8000
    locust -f locustfile.py --host http://localhost:8000 --headless -u 100 -r 20 -t 30s

Traffic mix mirrors a real shortener: mostly redirects, occasional link creation.

One account and a pool of links are created once, before load starts. Registering a
user per virtual user would mostly benchmark bcrypt (deliberately slow) instead of
the redirect path we actually care about.
"""
import random
import uuid

import requests
from locust import HttpUser, between, events, task

POOL_SIZE = 50
state = {"headers": {}, "codes": []}


@events.test_start.add_listener
def seed(environment, **_):
    host = environment.host.rstrip("/")
    creds = {"email": f"load-{uuid.uuid4().hex[:10]}@example.com", "password": "password123"}
    requests.post(f"{host}/api/auth/register", json=creds).raise_for_status()
    r = requests.post(f"{host}/api/auth/login", json=creds)
    r.raise_for_status()
    state["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    state["codes"] = []
    for i in range(POOL_SIZE):
        r = requests.post(
            f"{host}/api/links",
            json={"url": f"https://example.com/seed/{i}"},
            headers=state["headers"],
        )
        r.raise_for_status()
        state["codes"].append(r.json()["code"])


class ShortenerUser(HttpUser):
    wait_time = between(0.01, 0.1)

    @task(20)
    def redirect(self):
        self.client.get(
            f"/{random.choice(state['codes'])}",
            allow_redirects=False,  # measure our redirect, not the target site
            name="GET /{code}",
        )

    @task(1)
    def create(self):
        self.client.post(
            "/api/links",
            json={"url": f"https://example.com/page/{uuid.uuid4().hex}"},
            headers=state["headers"],
            name="POST /api/links",
        )
