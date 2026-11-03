"""Client IP resolution behind proxies, using the header chains observed in production."""
import pytest
from starlette.requests import Request

from app.config import Settings
from app.proxy import client_ip, from_trusted_edge

SECRET = "s3cret"


def req(headers=None, peer="10.0.0.9"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


def cfg(**kw):
    return Settings(**{"proxy_secret": None, "trusted_proxy_hops": 0, **kw})


# Through Vercel, as logged in production: some Vercel edges pass forged
# X-Forwarded-For / x-vercel-forwarded-for through, but Forwarded is Vercel's own.
VIA_VERCEL = {
    "x-forwarded-for": "6.6.6.6,13.126.34.128, 104.23.160.216, 10.29.222.54",
    "x-vercel-forwarded-for": "4.4.4.4",
    "forwarded": "for=103.23.29.122;host=url-shortener-pmhm.onrender.com;proto=https",
}
# Straight to Render with forged headers: the forged values sit left of the real client.
DIRECT_FORGED = {
    "x-forwarded-for": "6.6.6.6,103.23.29.125, 104.23.160.44, 10.31.43.5",
    "x-vercel-forwarded-for": "4.4.4.4",
}


def test_unconfigured_uses_socket_peer_and_ignores_headers():
    assert client_ip(req(DIRECT_FORGED), cfg()) == "10.0.0.9"


def test_hops_pick_the_entry_the_outermost_trusted_proxy_wrote():
    settings = cfg(trusted_proxy_hops=3)
    assert client_ip(req(DIRECT_FORGED), settings) == "103.23.29.125"  # forged 6.6.6.6 ignored
    # Through Vercel without the secret, the "client" is Vercel's server: safe, if coarse.
    assert client_ip(req(VIA_VERCEL), settings) == "13.126.34.128"


def test_short_chain_falls_back_to_leftmost_trusted_entry():
    assert client_ip(req({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}), cfg(trusted_proxy_hops=3)) == "1.2.3.4"


def test_vercel_forwarded_header_trusted_only_with_the_secret():
    settings = cfg(proxy_secret=SECRET, trusted_proxy_hops=3)
    assert client_ip(req({**VIA_VERCEL, "x-proxy-secret": SECRET}), settings) == "103.23.29.122"
    assert client_ip(req({**DIRECT_FORGED, "forwarded": "for=7.7.7.7"}), settings) == "103.23.29.125"
    assert client_ip(req({**DIRECT_FORGED, "x-proxy-secret": "guess"}), settings) == "103.23.29.125"
    assert client_ip(req(DIRECT_FORGED), settings) == "103.23.29.125"


@pytest.mark.parametrize(
    "header, expected",
    [
        ("for=1.2.3.4", "1.2.3.4"),
        ("for=9.9.9.9, for=1.2.3.4;proto=https", "1.2.3.4"),  # last element is the edge's
        ("for=1.2.3.4:4711", "1.2.3.4"),
        ('for="[2001:db8::1]:4711"', "2001:db8::1"),
        ("For=1.2.3.4", "1.2.3.4"),
    ],
)
def test_forwarded_header_parsing(header, expected):
    settings = cfg(proxy_secret=SECRET)
    assert client_ip(req({"forwarded": header, "x-proxy-secret": SECRET}), settings) == expected


def test_trusted_edge_without_forwarded_falls_back_to_hops():
    settings = cfg(proxy_secret=SECRET, trusted_proxy_hops=3)
    headers = {"x-forwarded-for": VIA_VERCEL["x-forwarded-for"], "x-proxy-secret": SECRET}
    assert client_ip(req(headers), settings) == "13.126.34.128"


@pytest.mark.parametrize("sent", [None, "", "guess", SECRET + "x"])
def test_edge_check_rejects_missing_or_wrong_secret(sent):
    headers = {"x-proxy-secret": sent} if sent is not None else {}
    assert not from_trusted_edge(req(headers), cfg(proxy_secret=SECRET))


def test_edge_check_off_when_no_secret_configured():
    assert not from_trusted_edge(req({"x-proxy-secret": ""}), cfg())


def test_forged_forwarded_for_cannot_dodge_rate_limit(client, auth, settings, monkeypatch):
    monkeypatch.setattr(settings, "create_rate_limit", 2)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    statuses = [
        client.post(
            "/api/links",
            json={"url": "https://example.com"},
            headers={**auth, "x-forwarded-for": f"9.9.9.{i}, 203.0.113.7"},
        ).status_code
        for i in range(4)
    ]
    assert statuses == [201, 201, 429, 429]
