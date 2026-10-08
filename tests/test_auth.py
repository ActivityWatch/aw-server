"""Tests for API key authentication middleware (aw_server/auth.py)."""

import pytest
from aw_server.server import AWFlask

# ── Config coercion (non-string api_key values) ─────────────────────────────


@pytest.mark.parametrize("raw_key", [True, False, 0, None, 12345, 3.14, ["k"]])
def test_non_string_api_key_disables_auth(raw_key):
    """A non-string api_key must not enable auth (disables it instead).

    Setting `api_key = true` in TOML used to produce key="True" — a trivially
    guessable string that looked like a boolean toggle. Any non-string value
    (booleans, numbers, containers) is a misconfiguration and must be
    treated as disabled, not stringified into a guessable key.
    """
    from aw_server.main import _coerce_api_key

    assert _coerce_api_key(raw_key) == ""


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


@pytest.mark.parametrize("scheme", ["bearer", "BEARER", "bEaReR"])
def test_bearer_scheme_is_case_insensitive(client, scheme):
    r = client.get("/api/0/buckets/", headers={"Authorization": f"{scheme} {KEY}"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "header", [f"Basic {KEY}", f"BearerX {KEY}", "Bearer", "Bearer ", f"bearer {KEY} "]
)
def test_invalid_authorization_returns_401(client, header):
    r = client.get("/api/0/buckets/", headers={"Authorization": header})
    assert r.status_code == 401


def test_static_files_are_public(client):
    """Non-/api paths (static files) are always accessible."""
    r = client.get("/")
    # 404 expected because there is no index.html in tests, but NOT 401.
    assert r.status_code != 401


# ── Path bypass hardening ────────────────────────────────────────────────────


def test_double_slash_does_not_bypass_auth(client):
    """//api/0/buckets/ is not a bypass vulnerability.

    Depending on the WSGI front-end, ``//api`` is either stripped as an
    authority component (404) or normalized to ``/api/...`` (then gated
    by the hook, which collapses empty segments → 401). Neither outcome
    may reach the protected handler unauthenticated.
    """
    r = client.get("//api/0/buckets/")
    assert r.status_code in (401, 404)


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


# ── Unicode / encoding robustness ───────────────────────────────────────────


@pytest.fixture(scope="module")
def unicode_client():
    app = AWFlask("127.0.0.1", testing=True, api_key="sécret-kéy-🔑")
    return app.test_client()


def test_non_ascii_key_accepts_correct_token(unicode_client):
    """A non-ASCII configured key must still authenticate the correct token."""
    r = unicode_client.get(
        "/api/0/buckets/", headers={"Authorization": "Bearer sécret-kéy-🔑"}
    )
    assert r.status_code == 200


def test_non_ascii_key_rejects_wrong_token(unicode_client):
    r = unicode_client.get("/api/0/buckets/", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_info_public_only_for_get(client):
    """The /api/0/info bypass is GET-only; other methods still require the key."""
    r = client.post("/api/0/info")
    assert r.status_code == 401
