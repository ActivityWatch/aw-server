"""Malformed client input must be rejected with 400 and a JSON message, not 500."""

import aw_datastore
import pytest
from aw_datastore import Datastore
from aw_query.exceptions import QueryException

from aw_server.api import ServerAPI

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


def assert_bad_request(r, expect: str):
    """400 with a JSON message that names the offending parameter/field/value."""
    assert r.status_code == 400, r.data
    assert r.is_json
    assert expect in r.json["message"], r.json


@pytest.mark.parametrize(
    "query,expect",
    [
        ("limit=abc", "limit"),
        ("start=garbage", "start"),
        ("end=garbage", "end"),
    ],
)
def test_get_events_bad_args(flask_client, bucket, query, expect):
    assert_bad_request(
        flask_client.get(f"/api/0/buckets/{bucket}/events?{query}"), expect
    )


@pytest.mark.parametrize("name", ["start", "end"])
def test_eventcount_bad_args(flask_client, bucket, name):
    assert_bad_request(
        flask_client.get(f"/api/0/buckets/{bucket}/events/count?{name}=garbage"),
        name,
    )


def test_heartbeat_bad_pulsetime(flask_client, bucket):
    assert_bad_request(
        flask_client.post(
            f"/api/0/buckets/{bucket}/heartbeat?pulsetime=abc",
            json={"timestamp": TS, "duration": 0, "data": {}},
        ),
        "pulsetime",
    )


BAD_EVENTS = [
    ({"timestamp": "not-a-date", "duration": 0, "data": {}}, "not-a-date"),
    ({"timestamp": TS, "duration": "abc", "data": {}}, "duration"),
]


@pytest.mark.parametrize(
    "event,expect",
    BAD_EVENTS
    + [({"timestamp": TS, "duration": 0, "data": {}, "unknown": 1}, "unknown")],
)
def test_post_events_bad_event(flask_client, bucket, event, expect):
    assert_bad_request(
        flask_client.post(f"/api/0/buckets/{bucket}/events", json=event), expect
    )
    assert_bad_request(
        flask_client.post(f"/api/0/buckets/{bucket}/events", json=[event]), expect
    )


@pytest.mark.parametrize("event,expect", BAD_EVENTS)
def test_heartbeat_bad_event(flask_client, bucket, event, expect):
    r = flask_client.post(f"/api/0/buckets/{bucket}/heartbeat?pulsetime=1", json=event)
    if expect == "duration":
        # rejected by the existing schema validation, which names the field
        assert r.status_code == 400, r.data
        assert "duration" in str(r.json)
    else:
        assert_bad_request(r, expect)


@pytest.mark.parametrize(
    "body,expect",
    [
        ({}, "type, client, hostname"),
        ({"client": "test", "type": "test"}, "hostname"),
    ],
)
def test_create_bucket_missing_fields(flask_client, body, expect):
    assert_bad_request(
        flask_client.post("/api/0/buckets/test-input-validation-missing", json=body),
        expect,
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


QUERY_START = "2024-01-01T00:00:00Z"
QUERY_END = "2024-01-02T00:00:00Z"
INVALID_QUERY_PERIODS = [
    f"{QUERY_START}/{QUERY_END}/ignored",
    f"{QUERY_START}/{QUERY_END}/",
    f"{QUERY_END}/{QUERY_START}",
    # Lexically ordered, but the start instant is later than the end instant.
    "2024-01-01T00:00:00-02:00/2024-01-01T01:00:00Z",
    QUERY_START,
    f"/{QUERY_END}",
    f"{QUERY_START}/",
    f"bad-date/{QUERY_END}",
    f"{QUERY_START}/bad-date",
]
VALID_QUERY_PERIODS = [
    f"{QUERY_START}/{QUERY_END}",
    f"{QUERY_START}/{QUERY_START}",
    # Equal instants in different offsets; comparison must use parsed datetimes.
    "2024-01-01T01:00:00+01:00/2024-01-01T00:00:00Z",
    # Lexically reversed, but start is before end in UTC.
    "2024-01-01T01:00:00+02:00/2024-01-01T00:00:00Z",
]


@pytest.fixture()
def query_api():
    db = Datastore(aw_datastore.get_storage_methods()["memory"], testing=True)
    return ServerAPI(db=db, testing=True)


@pytest.mark.parametrize("period", INVALID_QUERY_PERIODS)
@pytest.mark.parametrize("cache", [False, True])
def test_query_timeperiod_validation_api(query_api, monkeypatch, period, cache):
    def unexpected_call(*args, **kwargs):
        pytest.fail("Invalid period reached query evaluation or cache access")

    monkeypatch.setattr("aw_server.api.query2.query", unexpected_call)
    monkeypatch.setattr(query_api.query_cache, "cacheable", unexpected_call)
    with pytest.raises(QueryException) as exc:
        query_api.query2("validation", ["RETURN = 1;"], [period], cache=cache)
    assert period in str(exc.value)


@pytest.mark.parametrize("period", INVALID_QUERY_PERIODS)
@pytest.mark.parametrize("cache", [False, True])
def test_query_timeperiod_validation_http(flask_client, period, cache):
    response = flask_client.post(
        "/api/0/query/",
        json={"query": ["RETURN = 1;"], "timeperiods": [period], "cache": cache},
    )
    assert_bad_request(response, period)
    assert response.json["type"] == "QueryException"


@pytest.mark.parametrize("period", VALID_QUERY_PERIODS)
@pytest.mark.parametrize("cache", [False, True])
def test_query_timeperiod_validation_valid(query_api, flask_client, period, cache):
    for _ in range(2):
        assert query_api.query2("validation", ["RETURN = 1;"], [period], cache) == [1]
        response = flask_client.post(
            "/api/0/query/",
            json={"query": ["RETURN = 1;"], "timeperiods": [period], "cache": cache},
        )
        assert response.status_code == 200, response.data
        assert response.json == [1]
    assert query_api.query_cache.stats()["hits"] == (1 if cache else 0)


@pytest.mark.parametrize("cache", [False, True])
def test_query_timeperiod_validation_mixed_list(query_api, flask_client, cache):
    periods = [VALID_QUERY_PERIODS[0], INVALID_QUERY_PERIODS[0]]
    with pytest.raises(QueryException):
        query_api.query2("validation", ["RETURN = 1;"], periods, cache)
    response = flask_client.post(
        "/api/0/query/",
        json={"query": ["RETURN = 1;"], "timeperiods": periods, "cache": cache},
    )
    assert_bad_request(response, periods[1])
