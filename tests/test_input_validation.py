"""Malformed client input must be rejected with 400 and a JSON message, not 500."""

import pytest

BUCKET = "test-input-validation"
TS = "2026-01-01T00:00:00Z"


@pytest.fixture()
def bucket(flask_client):
    r = flask_client.post(
        f"/api/0/buckets/{BUCKET}",
        json={"client": "test", "type": "test", "hostname": "test"},
    )
    assert r.status_code == 200
    try:
        yield BUCKET
    finally:
        flask_client.delete(f"/api/0/buckets/{BUCKET}")


def assert_bad_request(r):
    assert r.status_code == 400, r.data
    assert r.is_json
    assert r.json["message"]


@pytest.mark.parametrize(
    "query",
    [
        "limit=abc",
        "start=garbage",
        "end=garbage",
    ],
)
def test_get_events_bad_args(flask_client, bucket, query):
    assert_bad_request(flask_client.get(f"/api/0/buckets/{bucket}/events?{query}"))


@pytest.mark.parametrize("query", ["start=garbage", "end=garbage"])
def test_eventcount_bad_args(flask_client, bucket, query):
    assert_bad_request(
        flask_client.get(f"/api/0/buckets/{bucket}/events/count?{query}")
    )


def test_heartbeat_bad_pulsetime(flask_client, bucket):
    assert_bad_request(
        flask_client.post(
            f"/api/0/buckets/{bucket}/heartbeat?pulsetime=abc",
            json={"timestamp": TS, "duration": 0, "data": {}},
        )
    )


@pytest.mark.parametrize(
    "event",
    [
        {"timestamp": "not-a-date", "duration": 0, "data": {}},
        {"timestamp": TS, "duration": "abc", "data": {}},
        {"timestamp": TS, "duration": 0, "data": {}, "unknown": 1},
    ],
)
def test_post_events_bad_event(flask_client, bucket, event):
    assert_bad_request(flask_client.post(f"/api/0/buckets/{bucket}/events", json=event))
    assert_bad_request(
        flask_client.post(f"/api/0/buckets/{bucket}/events", json=[event])
    )


@pytest.mark.parametrize(
    "event",
    [
        {"timestamp": "not-a-date", "duration": 0, "data": {}},
        {"timestamp": TS, "duration": "abc", "data": {}},
    ],
)
def test_heartbeat_bad_event(flask_client, bucket, event):
    assert_bad_request(
        flask_client.post(f"/api/0/buckets/{bucket}/heartbeat?pulsetime=1", json=event)
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"client": "test", "type": "test"},
    ],
)
def test_create_bucket_missing_fields(flask_client, body):
    assert_bad_request(
        flask_client.post("/api/0/buckets/test-input-validation-missing", json=body)
    )
    assert (
        flask_client.get("/api/0/buckets/test-input-validation-missing").status_code
        == 404
    )


def test_valid_input_still_accepted(flask_client, bucket):
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json={"timestamp": TS, "duration": 1.5, "data": {"a": 1}},
    )
    assert r.status_code == 200
    r = flask_client.get(f"/api/0/buckets/{bucket}/events?limit=10&start={TS}")
    assert r.status_code == 200
    assert len(r.json) == 1
    r = flask_client.get(
        f"/api/0/buckets/{bucket}/events/count?end=2027-01-01T00:00:00Z"
    )
    assert r.status_code == 200
    assert r.json == 1
