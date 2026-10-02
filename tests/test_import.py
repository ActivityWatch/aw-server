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


def test_import_duplicate_ids_within_export(flask_client, cleanup):
    cleanup.append("test-import-twice")
    r = flask_client.post(
        "/api/0/import",
        json={
            "buckets": {
                "a": _bucket("test-import-twice"),
                "b": _bucket("test-import-twice"),
            }
        },
    )
    assert r.status_code == 400
    assert "more than once" in r.json["message"]
    assert "test-import-twice" not in _buckets(flask_client)


def test_import_buckets_not_an_object(flask_client):
    r = flask_client.post("/api/0/import", json={"buckets": []})
    assert r.status_code == 400
    assert r.json["message"]


def test_import_multipart_failure_rolls_back_every_file(flask_client, cleanup):
    import io
    import json

    cleanup.extend(["test-import-file1", "test-import-file2"])
    good = {"buckets": {"test-import-file1": _bucket("test-import-file1")}}
    bad = {
        "buckets": {
            "test-import-file2": _bucket(
                "test-import-file2", events=[{"not": "an event"}]
            )
        }
    }
    r = flask_client.post(
        "/api/0/import",
        data={
            "file1": (io.BytesIO(json.dumps(good).encode()), "one.json"),
            "file2": (io.BytesIO(json.dumps(bad).encode()), "two.json"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    buckets = _buckets(flask_client)
    assert "test-import-file1" not in buckets
    assert "test-import-file2" not in buckets


def test_import_rollback_survives_delete_failure(
    flask_client, app, monkeypatch, cleanup
):
    """A failure while deleting one rolled-back bucket must not abort the
    rollback of the others, nor replace the original import error (which
    would turn the intended descriptive 400 into a 500)."""
    cleanup.extend(["test-import-rb-a", "test-import-rb-b"])

    def failing_delete(bucket_id):
        raise RuntimeError("simulated database error during rollback")

    monkeypatch.setattr(app.api, "delete_bucket", failing_delete)

    r = flask_client.post(
        "/api/0/import",
        json={
            "buckets": {
                "test-import-rb-a": _bucket("test-import-rb-a"),
                "test-import-rb-b": _bucket(
                    "test-import-rb-b", events=[{"not": "an event"}]
                ),
            }
        },
    )
    # The original client-fault error is preserved as a 400; the rollback's
    # RuntimeError (a non-client error) must not leak out as a 500.
    assert r.status_code == 400
    assert r.json["message"]
