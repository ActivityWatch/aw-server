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


def test_import_rollback_failure_is_reported_as_server_error(
    flask_client, app, monkeypatch, cleanup
):
    """If rollback cannot delete the buckets it created, the request must not
    report a clean client-fault 400: the buckets are still stored, so the
    incomplete rollback is surfaced as a server error."""
    cleanup.extend(["test-import-rb-a", "test-import-rb-b"])

    calls = []

    def failing_delete(bucket_id):
        calls.append(bucket_id)
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
    assert r.status_code == 500
    # Both buckets were attempted, so one failure did not abort the rollback.
    assert sorted(calls) == ["test-import-rb-a", "test-import-rb-b"]


def test_import_rollback_failure_does_not_abort_other_deletes(
    flask_client, app, monkeypatch, cleanup
):
    """A failure deleting one bucket must not abort the rollback of the others,
    and the bucket that could not be removed is reported honestly."""
    cleanup.extend(["test-import-rb-c", "test-import-rb-d"])
    original_delete = app.api.delete_bucket

    def flaky_delete(bucket_id):
        if bucket_id == "test-import-rb-c":
            raise RuntimeError("simulated database error during rollback")
        return original_delete(bucket_id)

    monkeypatch.setattr(app.api, "delete_bucket", flaky_delete)

    r = flask_client.post(
        "/api/0/import",
        json={
            "buckets": {
                "test-import-rb-c": _bucket("test-import-rb-c"),
                "test-import-rb-d": _bucket(
                    "test-import-rb-d", events=[{"not": "an event"}]
                ),
            }
        },
    )
    assert r.status_code == 500
    buckets = _buckets(flask_client)
    # The other bucket was still rolled back
    assert "test-import-rb-d" not in buckets
    # The one whose delete failed remains, which is why this returns a 500
    assert "test-import-rb-c" in buckets
