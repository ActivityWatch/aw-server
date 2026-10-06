import csv
import io
import json
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


def test_export_bucket_csv(flask_client, bucket):
    now = datetime(2026, 10, 6, 12, 0, 0, 123456)
    events = [
        {
            "timestamp": now.isoformat() + "+00:00",
            "duration": 1.5,
            "data": {"app": "Firefox", "title": 'a, "quoted" title'},
        },
        {
            "timestamp": (now + timedelta(seconds=2)).isoformat() + "+00:00",
            "duration": 0,
            "data": {"app": "=cmd", "count": 3, "flag": None},
        },
    ]
    r = flask_client.post(f"/api/0/buckets/{bucket}/events", json=events)
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/export/csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert (
        r.headers["Content-Disposition"]
        == f'attachment; filename="aw-events-export-{bucket}.csv"'
    )
    lines = r.get_data(as_text=True).split("\r\n")
    # Newest first, union of data keys, formula-looking values neutralized
    assert lines[0] == "id,timestamp,duration,app,count,flag,title"
    assert lines[1].endswith(
        ",2026-10-06T12:00:02.123000+00:00,0.000000000,'=cmd,3,null,"
    )
    assert lines[2].endswith(
        ',2026-10-06T12:00:00.123000+00:00,1.500000000,Firefox,,,"a, ""quoted"" title"'
    )
    assert lines[3] == ""

    r = flask_client.get(f"/api/0/buckets/{bucket}/export/csv?limit=1")
    assert len(r.get_data(as_text=True).split("\r\n")) == 3

    r = flask_client.get(f"/api/0/buckets/{bucket}/export/csv?start=notadate")
    assert r.status_code == 400

    r = flask_client.get("/api/0/buckets/does-not-exist/export/csv")
    assert r.status_code == 404


@pytest.mark.parametrize("n_keys", [32, 33])
def test_export_bucket_csv_wide(flask_client, bucket, n_keys):
    # Keys spread across events: the column decision uses their union
    keys = [f"k{i:02d}" for i in range(n_keys)]
    now = datetime(2026, 10, 6, 12, 0, 0)
    events = [
        {
            "timestamp": (now + timedelta(seconds=i)).isoformat() + "+00:00",
            "duration": 1,
            "data": {k: j for j, k in enumerate(chunk)},
        }
        for i, chunk in enumerate([keys[:16], keys[16:]])
    ]
    r = flask_client.post(f"/api/0/buckets/{bucket}/events", json=events)
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/export/csv")
    assert r.status_code == 200
    header, *rows = csv.reader(io.StringIO(r.get_data(as_text=True)))
    assert len(rows) == 2
    if n_keys <= 32:
        assert header == ["id", "timestamp", "duration"] + keys[16:] + keys[:16]
        assert all(len(row) == len(header) for row in rows)
    else:
        assert header == ["id", "timestamp", "duration", "data"]
        newest = rows[0][3]
        assert newest == json.dumps(
            events[1]["data"], separators=(",", ":")
        )  # compact JSON
        assert json.loads(rows[1][3]) == events[0]["data"]


def test_create_bucket_keeps_created_and_data(flask_client):
    # aw-sync creates pulled buckets with created + data ($aw.sync.origin)
    bucket_id = "test-synced-from-otherhost"
    try:
        r = flask_client.post(
            f"/api/0/buckets/{bucket_id}",
            json={
                "client": "aw-watcher-afk",
                "type": "afkstatus",
                "hostname": "otherhost",
                "created": "2026-09-26T22:39:59.959388+00:00",
                "data": {"$aw.sync.origin": "otherhost"},
            },
        )
        assert r.status_code == 200
        r = flask_client.get(f"/api/0/buckets/{bucket_id}")
        assert r.json["data"] == {"$aw.sync.origin": "otherhost"}
        assert r.json["created"].startswith("2026-09-26T22:39:59")

        r = flask_client.post(
            "/api/0/buckets/test-bad-data",
            json={"client": "c", "type": "t", "hostname": "h", "data": "nope"},
        )
        assert r.status_code == 400

        r = flask_client.post(
            "/api/0/buckets/test-empty-created",
            json={"client": "c", "type": "t", "hostname": "h", "created": ""},
        )
        assert r.status_code == 400
    finally:
        flask_client.delete(f"/api/0/buckets/{bucket_id}")


@pytest.mark.parametrize("n_inserted", [1, 2])
def test_heartbeat_after_insert_does_not_merge_into_stale_event(
    flask_client, bucket, n_inserted
):
    """Inserting events must invalidate the heartbeat cache.

    Otherwise a later heartbeat merges into the cached pre-insert event and
    replaces the newest stored event, losing an inserted one.
    """
    t = datetime(2026, 1, 1)

    def event(offset, label):
        return {
            "timestamp": (t + timedelta(seconds=offset)).isoformat(),
            "duration": 0.5,
            "data": {"label": label},
        }

    r = flask_client.post(
        f"/api/0/buckets/{bucket}/heartbeat?pulsetime=10", json=event(0, "a")
    )
    assert r.status_code == 200
    inserted = [event(1 + i, f"inserted-{i}") for i in range(n_inserted)]
    r = flask_client.post(f"/api/0/buckets/{bucket}/events", json=inserted)
    assert r.status_code == 200
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/heartbeat?pulsetime=10",
        json=event(1 + n_inserted, "a"),
    )
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/events")
    events = sorted(r.json, key=lambda e: e["timestamp"])
    assert [e["data"]["label"] for e in events] == [
        "a",
        *(f"inserted-{i}" for i in range(n_inserted)),
        "a",
    ]
    assert [e["duration"] for e in events] == [0.5] * (n_inserted + 2)


def test_heartbeat_after_delete_does_not_merge_into_deleted_event(flask_client, bucket):
    """Deleting events must invalidate the heartbeat cache.

    Otherwise a later heartbeat merges into the cached (deleted) event and
    replace_last() targets an event that no longer exists.
    """
    t = datetime(2026, 1, 1)

    def event(offset, label):
        return {
            "timestamp": (t + timedelta(seconds=offset)).isoformat(),
            "duration": 0.5,
            "data": {"label": label},
        }

    r = flask_client.post(
        f"/api/0/buckets/{bucket}/heartbeat?pulsetime=10", json=event(0, "a")
    )
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/events")
    stored = r.json[0]
    r = flask_client.delete(f"/api/0/buckets/{bucket}/events/{stored['id']}")
    assert r.status_code == 200

    # The heartbeat data matches the deleted cached event, so without the
    # cache invalidation it would merge into the deleted event and
    # replace_last() would operate on a nonexistent event.
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/heartbeat?pulsetime=10", json=event(1, "a")
    )
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/events")
    events = r.json
    assert len(events) == 1
    assert events[0]["data"]["label"] == "a"
    assert events[0]["duration"] == 0.5
    ts = datetime.fromisoformat(events[0]["timestamp"]).replace(tzinfo=None)
    assert ts == t + timedelta(seconds=1)


def test_export_bucket_csv_prefixes_colliding_data_keys(flask_client, bucket):
    data = {"app": "x", "duration": 7, "id": "a", "timestamp": "t"}
    r = flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json=[{"timestamp": "2026-10-06T12:00:00+00:00", "duration": 1, "data": data}],
    )
    assert r.status_code == 200

    r = flask_client.get(f"/api/0/buckets/{bucket}/export/csv")
    assert r.status_code == 200
    header, row = csv.reader(io.StringIO(r.get_data(as_text=True)))
    assert header[:3] == ["id", "timestamp", "duration"]
    columns = dict(zip(header[3:], row[3:]))
    assert columns == {
        "app": "x",
        "data.duration": "7",
        "data.id": "a",
        "data.timestamp": "t",
    }


def test_csv_header_prefix_repeats_until_unique():
    from aw_server.csv_export import _header_names

    assert _header_names(["id", "data.id"]) == [
        "id",
        "timestamp",
        "duration",
        "data.id",
        "data.data.id",
    ]
