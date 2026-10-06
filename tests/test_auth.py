"""Tests for API key authentication middleware (aw_server/auth.py)."""

import pytest
from aw_server.server import AWFlask


KEY = "test-secret-key"


@pytest.fixture(scope="module")
def auth_app():
    return AWFlask("127.0.0.1", testing=True, api_key=KEY)


@pytest.fixture(scope="module")
def client(auth_app):
    return auth_app.test_client()


# ── Unauthenticated client (no auth configured) ─────────────────────────────


def test_no_auth_app_passthrough(flask_client):
    """Default app (no api_key) allows all requests without a header."""
    r = flask_client.get("/api/0/info")
    assert r.status_code == 200

    r = flask_client.get("/api/0/buckets/")
    assert r.status_code == 200


# ── Auth-enabled: public endpoints ──────────────────────────────────────────


def test_info_is_public(client):
    """GET /api/0/info must succeed without a key."""
    r = client.get("/api/0/info")
    assert r.status_code == 200


def test_options_preflight_is_public(client):
    """OPTIONS to any /api/* path must not require a key (CORS preflight)."""
    r = client.options("/api/0/buckets/")
    assert r.status_code != 401


# ── Auth-enabled: protected endpoints ───────────────────────────────────────


def test_missing_key_returns_401(client):
    r = client.get("/api/0/buckets/")
    assert r.status_code == 401


def test_wrong_key_returns_401(client):
    r = client.get("/api/0/buckets/", headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code == 401


def test_correct_key_returns_200(client):
    r = client.get("/api/0/buckets/", headers={"Authorization": f"Bearer {KEY}"})
    assert r.status_code == 200


def test_static_files_are_public(client):
    """Non-/api paths (static files) are always accessible."""
    r = client.get("/")
    # 404 expected because there is no index.html in tests, but NOT 401.
    assert r.status_code != 401


# ── Path bypass hardening ────────────────────────────────────────────────────


def test_double_slash_does_not_reach_api(client):
    """//api/0/buckets/ is not a bypass vulnerability in Flask/Werkzeug.

    Werkzeug parses ``//api`` as an authority component, so request.path
    becomes ``/0/buckets/`` which has no route (404). The attacker cannot
    reach the real /api/0/buckets/ handler this way.
    """
    r = client.get("//api/0/buckets/")
    # 404 because Werkzeug strips the ``//api`` authority; not a bypass.
    assert r.status_code == 404


def test_percent_encoded_api_segment_is_gated(client):
    """/%61pi/0/buckets/ decodes to /api/0/buckets/ and must be gated.

    Werkzeug percent-decodes the path before our hook runs, so ``%61pi``
    becomes ``api`` and the segment list is [``api``, ``0``, ``buckets``].
    """
    r = client.get("/%61pi/0/buckets/")
    assert r.status_code == 401


def test_percent_encoded_info_is_still_public(client):
    """/%61pi/0/info decodes to /api/0/info and must remain public."""
    r = client.get("/%61pi/0/info")
    assert r.status_code == 200
