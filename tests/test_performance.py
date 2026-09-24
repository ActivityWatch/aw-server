import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from aw_core.models import Event

from aw_server import api as api_module
from aw_server import rest

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def setup_bucket(api):
    api.create_bucket("test", "test", "test", "test")
    return api.create_events(
        "test", [Event(timestamp=START, duration=1, data={"app": "a"})]
    )[0]


def test_heartbeat_uses_inserted_id_and_handles_intervening_mutations(isolated_api):
    api = isolated_api
    api.create_bucket("test", "test", "test", "test")
    first = api.heartbeat("test", Event(timestamp=START, data={"app": "a"}), 60)
    assert first.id is not None
    second = api.heartbeat(
        "test", Event(timestamp=START + timedelta(seconds=1), data={"app": "a"}), 60
    )
    assert second.id == first.id
    api.delete_event("test", first.id)
    replacement = api.heartbeat(
        "test", Event(timestamp=START + timedelta(seconds=2), data={"app": "a"}), 60
    )
    assert api.get_eventcount("test") == 1
    assert replacement.duration == timedelta(0)
    api.delete_bucket("test")
    api.create_bucket("test", "test", "test", "test")
    api.heartbeat(
        "test", Event(timestamp=START + timedelta(seconds=3), data={"app": "a"}), 60
    )
    assert api.get_eventcount("test") == 1


def test_failed_heartbeat_does_not_advance_cached_duration(isolated_api, monkeypatch):
    api = isolated_api
    setup_bucket(api)
    api.heartbeat(
        "test", Event(timestamp=START + timedelta(seconds=1), data={"app": "a"}), 60
    )
    before = api.last_event["test"].duration
    monkeypatch.setattr(
        api.db["test"], "replace", Mock(side_effect=RuntimeError("write failed"))
    )
    with pytest.raises(RuntimeError, match="write failed"):
        api.heartbeat(
            "test", Event(timestamp=START + timedelta(seconds=5), data={"app": "a"}), 60
        )
    assert api.last_event["test"].duration == before


def test_heartbeat_serializes_direct_api_calls(isolated_api):
    api = isolated_api
    if api.db.storage_strategy.sid != "memory":
        pytest.skip(
            "Memory backend isolates API synchronization from DB thread support"
        )
    api.create_bucket("test", "test", "test", "test")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: api.heartbeat(
                    "test", Event(timestamp=START, data={"app": "a"}), 60
                ),
                range(50),
            )
        )
    assert api.get_eventcount("test") == 1


def test_stream_export_matches_eager_export_and_is_lazy(isolated_api, monkeypatch):
    api = isolated_api
    setup_bucket(api)
    api.create_bucket("empty", "test", "test", "test")
    expected = {"buckets": api.export_all()}
    assert json.loads("".join(api.stream_export())) == expected
    assert json.loads("".join(api.stream_export("test"))) == {
        "buckets": {"test": expected["buckets"]["test"]}
    }
    monkeypatch.setattr(
        api.db.storage_strategy,
        "get_events",
        Mock(side_effect=AssertionError("eager read")),
    )
    # None of the built-in iterators should fall back to materializing get_events.
    assert json.loads("".join(api.stream_export())) == expected


def test_closing_export_closes_event_iterator(isolated_api, monkeypatch):
    api = isolated_api
    setup_bucket(api)
    consumed, closed = [], []

    def events():
        try:
            for _ in range(10000):
                consumed.append(True)
                yield Event(timestamp=START)
        finally:
            closed.append(True)

    monkeypatch.setattr(api.db["test"], "iter_events", events)
    stream = api.stream_export("test")
    while not consumed:
        next(stream)
    stream.close()
    assert 0 < len(consumed) < 10000
    assert closed == [True]


def test_http_stream_export(flask_client, app):
    response = flask_client.get("/api/0/export")
    assert response.status_code == 200
    assert response.is_streamed
    assert response.mimetype == "application/json"
    assert "buckets" in response.json
    assert flask_client.get("/api/0/buckets/missing/export").status_code == 404


def test_disabled_debug_logging_does_not_format_payload(isolated_api, monkeypatch, app):
    class Payload(dict):
        def __str__(self):
            raise AssertionError("payload was eagerly formatted")

    api = isolated_api
    api.create_bucket("test", "test", "test", "test")
    monkeypatch.setattr(api_module.logger, "level", logging.INFO)
    api.heartbeat("test", Event(timestamp=START, data=Payload(app="a")), 60)
    monkeypatch.setattr(rest.logger, "level", logging.INFO)
    with app.test_request_context("/api/0/buckets/test/events", method="POST"):
        monkeypatch.setattr(
            rest.request._get_current_object(),
            "get_json",
            lambda: Payload(timestamp=START, data={"app": "a"}),
        )
        monkeypatch.setattr(app.api, "create_events", lambda *args: [])
        assert rest.EventsResource().post("test") == ([], 200)
