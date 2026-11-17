"""query_max_events bounds how many events one query timeperiod may load (#187)."""

from datetime import datetime, timedelta, timezone

import aw_datastore
import pytest
from aw_core.models import Event
from aw_datastore import Datastore
from aw_query.exceptions import QueryException

from aw_server.api import ServerAPI

UTC = timezone.utc
START = datetime(2024, 1, 1, tzinfo=UTC)
DAY1 = f"{START.isoformat()}/{(START + timedelta(days=1)).isoformat()}"
DAY2 = f"{(START + timedelta(days=1)).isoformat()}/{(START + timedelta(days=2)).isoformat()}"
BOTH = f"{START.isoformat()}/{(START + timedelta(days=2)).isoformat()}"


def make_api(max_events: int) -> ServerAPI:
    db = Datastore(aw_datastore.get_storage_methods()["memory"], testing=True)
    api = ServerAPI(db=db, testing=True, query_cache=False, query_max_events=max_events)
    for bucket in ("a", "b"):
        api.create_bucket(bucket, "test", "test", "testhost")
        # 3 events on day 1, 3 on day 2
        api.create_events(
            bucket,
            [
                Event(
                    timestamp=START + timedelta(hours=6 + 24 * d + i),
                    duration=60,
                    data={"i": i},
                )
                for d in range(2)
                for i in range(3)
            ],
        )
    return api


def count(api, buckets, period):
    q = [f'e{i} = query_bucket("{b}");' for i, b in enumerate(buckets)]
    q.append("RETURN = [" + ", ".join(f"e{i}" for i in range(len(buckets))) + "];")
    return [len(e) for e in api.query2("test", q, [period])[0]]


def test_within_limit_returns_all_events():
    api = make_api(6)
    assert count(api, ["a", "b"], DAY1) == [3, 3]


def test_limit_counts_all_buckets_of_one_period(monkeypatch):
    api = make_api(5)
    storage = api.db.storage_strategy
    fetched = []
    real_get_events = storage.get_events

    def spy(bucket_id, *args, **kwargs):
        fetched.append(bucket_id)
        return real_get_events(bucket_id, *args, **kwargs)

    monkeypatch.setattr(storage, "get_events", spy)
    with pytest.raises(QueryException, match="more than the server limit of 5"):
        count(api, ["a", "b"], DAY1)
    # The rejected bucket must fail on its COUNT, before its events are loaded.
    assert fetched == ["a"]


def test_limit_applies_per_timeperiod():
    api = make_api(6)
    q = ['e = query_bucket("a"); f = query_bucket("b");', "RETURN = [e, f];"]
    # each period loads 6 events: allowed, even though the request loads 12
    assert len(api.query2("test", q, [DAY1, DAY2])) == 2
    with pytest.raises(
        QueryException, match="Query would load 12 events \\(bucket 'b' alone has 6"
    ):
        count(api, ["a", "b"], BOTH)


def test_zero_disables_limit():
    api = make_api(0)
    assert count(api, ["a", "b"], BOTH) == [6, 6]


def test_over_limit_query_is_a_400(flask_client):
    app_api = flask_client.application.api
    old = app_api.query_max_events
    bucket = "test-query-limit"
    flask_client.post(
        f"/api/0/buckets/{bucket}", json={"client": "t", "type": "t", "hostname": "h"}
    )
    flask_client.post(
        f"/api/0/buckets/{bucket}/events",
        json=[
            {
                "timestamp": (START + timedelta(hours=i)).isoformat(),
                "duration": 1,
                "data": {},
            }
            for i in range(3)
        ],
    )
    app_api.query_max_events = 2
    try:
        r = flask_client.post(
            "/api/0/query/",
            json={
                "query": [f'RETURN = query_bucket("{bucket}");'],
                "timeperiods": [DAY1],
            },
        )
    finally:
        app_api.query_max_events = old
        flask_client.delete(f"/api/0/buckets/{bucket}?force=1")
    assert r.status_code == 400
    assert "query_max_events" in r.json["message"]
