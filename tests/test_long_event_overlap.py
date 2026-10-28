"""REST, CSV and AQL must include accepted long events with Peewee storage.

Requires an aw-core containing the repair for ActivityWatch/aw-core#194.
"""

import csv
import io
from functools import partial

import pytest
from aw_datastore.storages import PeeweeStorage

from aw_server.server import AWFlask

ROUTE = "/api/0/buckets/long-events"
START = "2026-10-02T12:00:00+00:00"
END = "2026-10-02T13:00:00+00:00"
BOUNDS = {"start": START, "end": END}


@pytest.fixture()
def long_client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aw_datastore.storages.peewee.get_data_dir", lambda _: str(tmp_path)
    )
    app = AWFlask(
        "127.0.0.1",
        testing=True,
        storage_method=partial(PeeweeStorage, filepath=str(tmp_path / "events.db")),
        query_cache=False,
    )
    client = app.test_client()
    assert (
        client.post(
            ROUTE, json={"type": "test", "client": "test", "hostname": "test"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            ROUTE + "/events",
            json={
                "timestamp": "2026-10-01T00:00:00Z",
                "duration": 172800,
                "data": {"label": "long"},
            },
        ).status_code
        == 200
    )
    try:
        yield client
    finally:
        app.api.db.storage_strategy.db.close()


def test_bounded_get_and_count_include_long_event(long_client):
    unbounded = long_client.get(ROUTE + "/events").get_json()
    assert len(unbounded) == 1
    assert unbounded[0]["duration"] == 172800
    response = long_client.get(ROUTE + "/events", query_string=BOUNDS)
    assert response.status_code == 200
    events = response.get_json()
    assert len(events) == 1
    assert events[0] == dict(unbounded[0], timestamp=START, duration=3600.0)
    response = long_client.get(ROUTE + "/events/count", query_string=BOUNDS)
    assert response.status_code == 200
    assert response.get_json() == 1
    assert long_client.get(ROUTE + "/events").get_json() == unbounded


def test_bounded_csv_contains_long_event_row(long_client):
    unbounded = long_client.get(ROUTE + "/events").get_json()
    assert len(unbounded) == 1
    assert unbounded[0]["duration"] == 172800
    response = long_client.get(ROUTE + "/export/csv", query_string=BOUNDS)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert len(rows) == 1
    assert rows[0]["label"] == "long"
    assert rows[0]["timestamp"] == START
    assert float(rows[0]["duration"]) == 3600
    assert long_client.get(ROUTE + "/events").get_json() == unbounded


@pytest.mark.parametrize(
    "query,expected",
    [
        ('RETURN = sum_durations(query_bucket("long-events"));', 3600.0),
        ('RETURN = query_bucket_eventcount("long-events");', 1),
    ],
)
def test_bounded_aql_includes_long_event(long_client, query, expected):
    unbounded = long_client.get(ROUTE + "/events").get_json()
    assert len(unbounded) == 1
    assert unbounded[0]["duration"] == 172800
    response = long_client.post(
        "/api/0/query/",
        json={"query": [query], "timeperiods": [START + "/" + END], "cache": False},
    )
    assert response.status_code == 200
    # Preserve Peewee's existing clipping semantics; do not sum the full 48h.
    assert response.get_json() == [expected]
    assert long_client.get(ROUTE + "/events").get_json() == unbounded
