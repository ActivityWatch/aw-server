import random
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from aw_core.models import Event

from aw_server.exceptions import NotFound


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
    assert r.json["profile"] == "testing"


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
    assert len(r.json) == 0


# TODO: Add benchmark for basic AFK-filtering query


def test_query_invalid_timeperiod(flask_client):
    """Malformed timeperiods must yield 400 (client error), not 500.

    Regression test: a non-ISO8601 timeperiod previously raised an uncaught
    iso8601.ParseError, surfacing as an Internal Server Error.
    """
    r = flask_client.post(
        "/api/0/query/",
        json={"query": ["RETURN = 1;"], "timeperiods": ["not-a-valid-period"]},
    )
    assert r.status_code == 400
    assert "not-a-valid-period" in r.json["message"]


def test_query_timeperiod_missing_slash(flask_client):
    """A timeperiod without a start/end slash separator must yield 400, not 500.

    Regression test: a single ISO8601 datetime (no slash) previously raised an
    uncaught IndexError when indexing the split result.
    """
    r = flask_client.post(
        "/api/0/query/",
        json={"query": ["RETURN = 1;"], "timeperiods": ["2024-01-01T00:00:00+00:00"]},
    )
    assert r.status_code == 400


def test_query_valid_timeperiod(flask_client):
    """A well-formed query with a valid timeperiod still succeeds."""
    r = flask_client.post(
        "/api/0/query/",
        json={
            "query": ["RETURN = 1;"],
            "timeperiods": ["2024-01-01T00:00:00+00:00/2024-01-02T00:00:00+00:00"],
        },
    )
    assert r.status_code == 200
    assert r.json == [1]


def test_bucket_checks_reuse_datastore_lookup(isolated_api, monkeypatch):
    api = isolated_api
    api.create_bucket("test", "test", "test", "test")
    # Simulate the first access to a bucket that existed before server startup.
    api.db.bucket_instances.clear()
    listing = Mock(wraps=api.db.buckets)
    monkeypatch.setattr(api.db, "buckets", listing)

    assert api.get_events("test") == []
    listing.assert_not_called()
    listing.reset_mock()

    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    api.heartbeat("test", Event(timestamp=timestamp, data={"app": "test"}), 60)
    merged = api.heartbeat(
        "test",
        Event(timestamp=timestamp + timedelta(seconds=1), data={"app": "test"}),
        60,
    )
    assert merged.duration == timedelta(seconds=1)
    assert api.get_eventcount("test") == 1
    assert len(api.get_events("test")) == 1
    assert len(api.export_bucket("test")["events"]) == 1
    listing.assert_not_called()


def test_bucket_checks_follow_datastore_lifecycle(isolated_api):
    api = isolated_api
    with pytest.raises(NotFound, match="There's no bucket named test"):
        api.get_events("test")

    api.create_bucket("test", "test", "test", "test")
    assert api.get_events("test") == []
    api.delete_bucket("test")
    with pytest.raises(NotFound, match="There's no bucket named test"):
        api.get_events("test")

    # Changes made through Datastore must also be visible to the API.
    api.db.create_bucket("test", type="test", client="test", hostname="test")
    assert api.get_events("test") == []
    api.db.delete_bucket("test")
    with pytest.raises(NotFound):
        api.get_events("test")


def test_bucket_check_does_not_mask_operation_errors(isolated_api, monkeypatch):
    api = isolated_api
    api.create_bucket("test", "test", "test", "test")
    monkeypatch.setattr(api.db["test"], "get", Mock(side_effect=KeyError("event data")))
    with pytest.raises(KeyError, match="event data"):
        api.get_events("test")
