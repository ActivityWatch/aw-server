"""A web page on another origin must not be able to import data.

A multipart/form-data POST is a CORS "simple request": the browser sends it
without a preflight, so CORS only hides the response from the page while the
import still runs. /api/0/import is the only state-changing endpoint that
accepts such a body (the others require application/json, which forces a
preflight), so it checks the Origin header itself.
"""

import io
import json
from datetime import datetime, timezone

import pytest

from aw_server.server import AWFlask

_HOST = "127.0.0.1"


def _export(bucket_id):
    return {
        "buckets": {
            bucket_id: {
                "id": bucket_id,
                "type": "test",
                "client": "test",
                "hostname": "test",
                "created": datetime.now(timezone.utc).isoformat(),
                "events": [],
            }
        }
    }


def _upload(client, bucket_id, origin=None, host="localhost:5600"):
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    body = json.dumps(_export(bucket_id)).encode()
    return client.post(
        "/api/0/import",
        data={"file": (io.BytesIO(body), "export.json")},
        content_type="multipart/form-data",
        headers=headers,
    )


@pytest.fixture()
def client():
    app = AWFlask(_HOST, testing=True, cors_origins=["https://configured.example"])
    client = app.test_client()
    yield client
    for bucket_id in client.get(
        "/api/0/buckets/", headers={"Host": "localhost:5600"}
    ).json:
        if bucket_id.startswith("test-origin-"):
            client.delete(
                f"/api/0/buckets/{bucket_id}", headers={"Host": "localhost:5600"}
            )


def _bucket_ids(client):
    return client.get("/api/0/buckets/", headers={"Host": "localhost:5600"}).json


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_cross_origin_multipart_import_is_rejected(client, origin):
    r = _upload(client, "test-origin-evil", origin=origin)
    assert r.status_code == 403
    assert "test-origin-evil" not in _bucket_ids(client)


def test_cross_origin_json_import_is_rejected(client):
    r = client.post(
        "/api/0/import",
        json=_export("test-origin-json"),
        headers={"Host": "localhost:5600", "Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert "test-origin-json" not in _bucket_ids(client)


@pytest.mark.parametrize(
    "origin",
    [
        None,  # aw-client and other non-browser clients send no Origin
        "http://localhost:5600",  # the bundled web UI
        "http://LOCALHOST:5600",
        "https://configured.example",  # explicit cors_origins opt-in
        "http://127.0.0.1:27180",  # aw-webui dev server in testing mode
    ],
)
def test_same_or_configured_origin_import_is_accepted(client, origin):
    r = _upload(client, "test-origin-ok", origin=origin)
    assert r.status_code == 200, r.json
    assert "test-origin-ok" in _bucket_ids(client)


@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost:5600",  # same host and port, different scheme
        "http://[::1",  # malformed: urlsplit raises ValueError
    ],
)
def test_scheme_mismatch_and_malformed_origin_are_rejected(client, origin):
    r = _upload(client, "test-origin-bad", origin=origin)
    assert r.status_code == 403
    assert "test-origin-bad" not in _bucket_ids(client)


def test_wildcard_cors_origin_allows_import():
    # Flask-CORS treats "*" as every origin; an owner who opted into that
    # should not then be refused by the import check.
    app = AWFlask(_HOST, testing=True, cors_origins=["*"])
    client = app.test_client()
    r = _upload(client, "test-origin-wildcard", origin="https://other.example")
    assert r.status_code == 200, r.json
    client.delete(
        "/api/0/buckets/test-origin-wildcard", headers={"Host": "localhost:5600"}
    )


def test_shared_cors_origin_list_is_not_mutated():
    origins = ["https://configured.example"]
    AWFlask(_HOST, testing=True, cors_origins=origins)
    assert origins == ["https://configured.example"]
