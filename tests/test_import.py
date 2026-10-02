from datetime import datetime, timezone

import pytest


def _bucket(bucket_id, events=None):
    return {
        "id": bucket_id,
        "type": "test",
        "client": "test",
        "hostname": "test",
        "created": datetime.now(timezone.utc).isoformat(),
        "events": (
            events
            if events is not None
            else [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration": 1,
                    "data": {"label": "imported"},
                }
            ]
        ),
    }


@pytest.fixture()
def cleanup(flask_client):
    ids = []
    yield ids
    buckets = flask_client.get("/api/0/buckets/").json
    for bucket_id in ids:
        if bucket_id in buckets:
            flask_client.delete(f"/api/0/buckets/{bucket_id}")


def _buckets(flask_client):
    return flask_client.get("/api/0/buckets/").json


def test_import_success(flask_client, cleanup):
    cleanup.append("test-import-ok")
    r = flask_client.post(
        "/api/0/import", json={"buckets": {"test-import-ok": _bucket("test-import-ok")}}
    )
    assert r.status_code == 200
    assert r.json == {"message": "Import successful"}
    events = flask_client.get("/api/0/buckets/test-import-ok/events").json
    assert len(events) == 1


def test_import_duplicate_bucket(flask_client, cleanup):
    cleanup.append("test-import-dup")
    payload = {"buckets": {"test-import-dup": _bucket("test-import-dup")}}
    assert flask_client.post("/api/0/import", json=payload).status_code == 200

    r = flask_client.post("/api/0/import", json=payload)
    assert r.status_code == 400
    assert "already exists" in r.json["message"]
    # The existing bucket is untouched, not duplicated or deleted.
    events = flask_client.get("/api/0/buckets/test-import-dup/events").json
    assert len(events) == 1


def test_import_duplicate_rolls_back_earlier_buckets(flask_client, cleanup):
    cleanup.extend(["test-import-existing", "test-import-new"])
    existing = {"buckets": {"test-import-existing": _bucket("test-import-existing")}}
    assert flask_client.post("/api/0/import", json=existing).status_code == 200

    r = flask_client.post(
        "/api/0/import",
        json={
            "buckets": {
                "test-import-new": _bucket("test-import-new"),
                "test-import-existing": _bucket("test-import-existing"),
            }
        },
    )
    assert r.status_code == 400
    buckets = _buckets(flask_client)
    assert "test-import-new" not in buckets
    assert "test-import-existing" in buckets


def test_import_bad_events_rolls_back_failing_bucket(flask_client, cleanup):
    cleanup.append("test-import-badevents")
    r = flask_client.post(
        "/api/0/import",
        json={
            "buckets": {
                "test-import-badevents": _bucket(
                    "test-import-badevents", events=[{"not": "an event"}]
                )
            }
        },
    )
    assert r.status_code == 400
    assert r.json["message"]
    assert "test-import-badevents" not in _buckets(flask_client)


def test_import_missing_buckets_key(flask_client):
    r = flask_client.post("/api/0/import", json={"nope": {}})
    assert r.status_code == 400
    assert r.json["message"]


def test_import_malformed_json(flask_client):
    r = flask_client.post(
        "/api/0/import", data="{not json", content_type="application/json"
    )
    assert r.status_code == 400
