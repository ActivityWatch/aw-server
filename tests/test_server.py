import random
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def bucket(flask_client):
    "Context manager for creating and deleting a testing bucket"
    try:
        bucket_id = "test"
        r = flask_client.post(
            f"/api/0/buckets/{bucket_id}",
            json={"client": "test", "type": "test", "hostname": "test"},
        )
        assert r.status_code == 200
        yield bucket_id
    finally:
        r = flask_client.delete(f"/api/0/buckets/{bucket_id}")
        assert r.status_code == 200


def test_info(flask_client):
    r = flask_client.get("/api/0/info")
    assert r.status_code == 200
    assert r.json["testing"]


def test_buckets(flask_client, bucket, benchmark):
    @benchmark
    def list_buckets():
        r = flask_client.get("/api/0/buckets/")
        print(r.json)
        assert r.status_code == 200
        assert len(r.json) == 1


def test_heartbeats(flask_client, bucket, benchmark):
    # FIXME: Currently tests using the memory storage method
    # TODO: Test with a longer data section and see if there's a significant difference
    # TODO: Test with a larger bucket and see if there's a significant difference
    @benchmark
    def heartbeat():
        now = datetime.now()
        r = flask_client.post(
            f"/api/0/buckets/{bucket}/heartbeat?pulsetime=1",
            json={"timestamp": now, "duration": 0, "data": {"random": random.random()}},
        )
        assert r.status_code == 200


def test_get_events(flask_client, bucket, benchmark):
    n_events = 100
    start_time = datetime.now() - timedelta(days=100)
    for i in range(n_events):
        now = start_time + timedelta(hours=i)
        r = flask_client.post(
            f"/api/0/buckets/{bucket}/heartbeat?pulsetime=0",
            json={"timestamp": now, "duration": 0, "data": {"random": random.random()}},
        )
        assert r.status_code == 200

    @benchmark
    def get_events():
        r = flask_client.get(f"/api/0/buckets/{bucket}/events")
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get(f"/api/0/buckets/{bucket}/events?limit=-1")
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get(f"/api/0/buckets/{bucket}/events?limit=10")
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == 10

        r = flask_client.get(f"/api/0/buckets/{bucket}/events?limit=100")
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get(f"/api/0/buckets/{bucket}/events?limit=1000")
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events


def test_insert_event_returns_list(flask_client, bucket):
    """Test that POST /events returns a list of events with IDs (matching aw-server-rust)."""
    now = datetime.now()
    event_data = {
        "timestamp": now.isoformat(),
        "duration": 0,
        "data": {"label": "test"},
    }

    # Single event as list
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json=[event_data],
    )
    assert r.status_code == 200
    assert isinstance(r.json, list), f"Expected list, got {type(r.json)}"
    assert len(r.json) == 1
    assert r.json[0]["id"] is not None
    assert r.json[0]["data"] == {"label": "test"}

    # Single event as dict (legacy format)
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json=event_data,
    )
    assert r.status_code == 200
    assert isinstance(r.json, list), f"Expected list, got {type(r.json)}"
    assert len(r.json) == 1
    assert r.json[0]["id"] is not None


def test_insert_events_returns_list(flask_client, bucket):
    """Test that POST /events with multiple events returns a list."""
    now = datetime.now()
    events_data = [
        {
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "duration": 0,
            "data": {"label": f"test-{i}"},
        }
        for i in range(3)
    ]

    r = flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json=events_data,
    )
    assert r.status_code == 200
    assert isinstance(r.json, list), f"Expected list, got {type(r.json)}"
    assert len(r.json) == 3


# TODO: Add benchmark for basic AFK-filtering query
