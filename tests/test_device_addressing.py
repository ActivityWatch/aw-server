"""Device HTTP contract against the real pair-keyed SQLite datastore."""

from functools import partial

import pytest
from aw_datastore.storages import SqliteStorage

from aw_server.server import AWFlask


@pytest.fixture()
def device_app(tmp_path, monkeypatch):
    monkeypatch.setattr("aw_server.api.get_device_id", lambda: "server-uuid")
    app = AWFlask(
        "127.0.0.1",
        testing=True,
        storage_method=partial(SqliteStorage, filepath=str(tmp_path / "events.db")),
        cors_origins=[],
    )
    yield app
    app.api.db.storage_strategy.conn.close()


def create(client, device, bid="window", hostname="host"):
    return client.post(
        f"/api/0/devices/{device}/buckets/{bid}",
        json={
            "client": "test",
            "type": "test",
            "hostname": hostname,
        },
    )


def event(label, second=0):
    return {
        "timestamp": f"2024-01-01T12:00:{second:02d}Z",
        "duration": 1,
        "data": {"label": label},
    }


def test_scoped_crud_uuid_alias_and_legacy_conflict(device_app):
    c = device_app.test_client()
    assert create(c, "local").status_code == 200
    assert create(c, "server-uuid").status_code == 304
    assert create(c, "peer").status_code == 200
    for device in ("local", "peer"):
        base = f"/api/0/devices/{device}/buckets/window"
        r = c.post(base + "/events", json=event(device))
        assert r.status_code == 200
        eid = r.json[0]["id"]
        assert c.get(base + "/events/count").json == 1
        assert c.get(base + f"/events/{eid}").json["data"] == {"label": device}
        assert c.get(base).json["device_id"] == device
    assert c.get("/api/0/devices/server-uuid/buckets/window/events").json[0][
        "data"
    ] == {"label": "local"}
    for path in ("/buckets/", "/buckets/window", "/buckets/window/events", "/export"):
        assert c.get("/api/0" + path).status_code == 409
    assert c.delete("/api/0/devices/local/buckets/window").status_code == 200
    assert c.get("/api/0/devices/peer/buckets/window/events/count").json == 1


def test_query_cache_is_scoped_and_invalidated(device_app):
    c = device_app.test_client()
    query = {
        "query": ['RETURN = query_bucket("window");'],
        "timeperiods": ["2024-01-01T00:00:00Z/2024-01-02T00:00:00Z"],
    }
    for device in ("local", "peer"):
        assert create(c, device).status_code == 200
        assert (
            c.post(
                f"/api/0/devices/{device}/buckets/window/events", json=event(device)
            ).status_code
            == 200
        )
        for _ in range(2):
            r = c.post(f"/api/0/devices/{device}/query", json=query)
            assert r.status_code == 200
            assert r.json[0][0]["data"] == {"label": device}
    assert c.post("/api/0/query/", json=query).status_code == 409
    assert (
        c.post(
            "/api/0/devices/server-uuid/buckets/window/events", json=event("new", 5)
        ).status_code
        == 200
    )
    assert len(c.post("/api/0/devices/local/query", json=query).json[0]) == 2
    assert len(c.post("/api/0/devices/peer/query", json=query).json[0]) == 1


def test_alias_heartbeat_and_metadata_repair(device_app):
    c = device_app.test_client()
    assert create(c, "local", "window_old_host", "old_host").status_code == 200
    assert create(c, "local", "window", "old_host").status_code == 304
    for device, bid in (("local", "window"), ("server-uuid", "window_old_host")):
        r = c.post(
            f"/api/0/devices/{device}/buckets/{bid}/heartbeat?pulsetime=10",
            json=event("same", 0 if device == "local" else 5),
        )
        assert r.status_code == 200
    assert c.get("/api/0/devices/local/buckets/window/events/count").json == 1
    assert create(c, "peer", "window", "!local").status_code == 400
    # The storage anti-shadowing guard deliberately still rejects an exact peer
    # name that would redirect the established global alias.
    assert create(c, "peer", "window", "peer_host").status_code == 409
    assert create(c, "peer", "window_old_host", "peer_host").status_code == 200
    assert (
        c.post(
            "/api/0/devices/peer/buckets/window_old_host/heartbeat?pulsetime=10",
            json=event("peer", 6),
        ).status_code
        == 200
    )
    assert c.get("/api/0/devices/local/buckets/window/events").json[0]["data"] == {
        "label": "same"
    }
    assert (
        c.put(
            "/api/0/devices/local/buckets/window_old_host",
            json={"hostname": "new_host"},
        ).status_code
        == 200
    )
    assert c.get("/api/0/devices/local/buckets/window").status_code == 404
    assert c.get("/api/0/devices/local/buckets/window_old_host").status_code == 200


def test_legacy_post_is_local_and_alias_aware(device_app):
    c = device_app.test_client()
    assert create(c, "peer", "peer_only").status_code == 200
    r = c.post(
        "/api/0/buckets/local_new",
        json={
            "client": "test",
            "type": "test",
            "hostname": "!local",
            "device_id": "peer",
        },
    )
    assert r.status_code == 200
    assert c.get("/api/0/devices/local/buckets/local_new").json["device_id"] == "local"
    assert c.get("/api/0/devices/peer/buckets/local_new").status_code == 404
    assert create(c, "local", "old_host", "host").status_code == 200
    assert (
        c.post(
            "/api/0/buckets/old",
            json={"client": "test", "type": "test", "hostname": "host"},
        ).status_code
        == 304
    )


def test_grouped_catalogue_export_roundtrip_and_preflight(
    device_app, tmp_path, monkeypatch
):
    c = device_app.test_client()
    assert c.get("/api/0/devices/buckets").json == {
        "devices": {"server-uuid": {"buckets": {}}}
    }
    for device in ("local", "peer"):
        assert create(c, device).status_code == 200
        assert (
            c.post(
                f"/api/0/devices/{device}/buckets/window/events", json=event(device)
            ).status_code
            == 200
        )
    assert {d["id"] for d in c.get("/api/0/devices").json} == {"server-uuid", "peer"}
    exported = c.get("/api/0/devices/export")
    assert exported.status_code == 200
    assert (
        exported.json["devices"]["server-uuid"]["buckets"]["window"]["device_id"]
        == "server-uuid"
    )
    monkeypatch.setattr("aw_server.api.get_device_id", lambda: "destination-uuid")
    destination = AWFlask(
        "127.0.0.1",
        testing=True,
        cors_origins=[],
        storage_method=partial(
            SqliteStorage, filepath=str(tmp_path / "destination.db")
        ),
    )
    try:
        dc = destination.test_client()
        assert dc.post("/api/0/devices/import", json=exported.json).status_code == 200
        assert dc.get("/api/0/devices/local/buckets/window").status_code == 404
        for device in ("server-uuid", "peer"):
            assert dc.get(f"/api/0/devices/{device}/buckets/window/events").json[0][
                "data"
            ]["label"] == ("local" if device == "server-uuid" else "peer")
        # Reject the entire malformed envelope before writing the first group.
        invalid = {
            "devices": {
                "fresh": {
                    "buckets": {
                        "fresh": {
                            "id": "fresh",
                            "device_id": "fresh",
                            "hostname": "h",
                            "client": "c",
                            "type": "t",
                            "created": "2024-01-01T00:00:00Z",
                            "events": [],
                        }
                    }
                },
                "local": {"buckets": {}},
            }
        }
        assert dc.post("/api/0/devices/import", json=invalid).status_code == 400
        assert dc.get("/api/0/devices/fresh/buckets/").json == {}
    finally:
        destination.api.db.storage_strategy.conn.close()


def test_scoped_export_delete_and_api_key(device_app):
    from aw_server import auth

    auth.register(device_app, "secret")
    c = device_app.test_client()
    for path in (
        "/api/0/devices/local/buckets/",
        "/api/0/devices/export",
        "/api/0/devices/buckets",
    ):
        assert c.get(path).status_code == 401
    c.environ_base["HTTP_AUTHORIZATION"] = "Bearer secret"
    assert create(c, "local").status_code == 200
    base = "/api/0/devices/local/buckets/window"
    eid = c.post(base + "/events", json=event("local")).json[0]["id"]
    assert c.get(base + "/export").json["buckets"]["window"]["events"][0]["data"] == {
        "label": "local"
    }
    assert c.get(base + "/export/csv").status_code == 200
    assert c.post(base + "/events/delete", json={"ids": [eid]}).status_code == 200
    assert c.get(base + "/events/count").json == 0


def test_import_preserves_metadata_and_rejects_alias_split(device_app):
    c = device_app.test_client()
    bucket = {
        "id": "history_host",
        "device_id": "source",
        "client": "c",
        "type": "t",
        "hostname": "host",
        "created": "2024-01-01T00:00:00Z",
        "data": {"custom": "preserved"},
        "events": [event("source")],
    }
    envelope = {"devices": {"source": {"buckets": {"history_host": bucket}}}}
    assert c.post("/api/0/devices/import", json=envelope).status_code == 200
    assert c.get("/api/0/devices/source/buckets/history").json["data"] == bucket["data"]
    # A later import alias cannot create an empty canonical row over history.
    bucket["id"] = "history"
    envelope["devices"]["source"]["buckets"] = {"history": bucket}
    assert c.post("/api/0/devices/import", json=envelope).status_code == 400
    assert c.get("/api/0/devices/source/buckets/history/events/count").json == 1


def test_scoped_heartbeat_invalidates_after_insert_and_delete(device_app):
    c = device_app.test_client()
    assert create(c, "local").status_code == 200
    base = "/api/0/devices/local/buckets/window"
    assert c.post(base + "/heartbeat?pulsetime=10", json=event("a")).status_code == 200
    inserted = c.post(base + "/events", json=event("b", 2)).json[0]["id"]
    assert (
        c.post(base + "/heartbeat?pulsetime=10", json=event("a", 4)).status_code == 200
    )
    assert c.get(base + "/events/count").json == 3
    assert c.delete(base + f"/events/{inserted}").status_code == 200
    assert c.get(base + "/events/count").json == 2


def test_unsupported_scoped_backend_fails_closed(monkeypatch):
    monkeypatch.setattr("aw_server.api.get_device_id", lambda: "server-uuid")
    c = AWFlask("127.0.0.1", testing=True, cors_origins=[]).test_client()
    assert create(c, "peer").status_code == 501
    assert c.get("/api/0/buckets/").json == {}


def test_legacy_post_does_not_acknowledge_alias_for_a_different_global_target(
    device_app,
):
    db = device_app.api.db.storage_strategy
    local = db.for_device("local")
    local.create_bucket("window_host", "t", "c", "host", "2024-01-01T00:00:00Z")
    # Simulate a pre-existing catalogue from before the anti-shadowing guard.
    db.conn.execute(
        "INSERT INTO buckets(id, device_id, type, client, hostname, created, datastr) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("window", "peer", "t", "c", "peer-host", "2024-01-01T00:00:00Z", "{}"),
    )
    db.commit()
    c = device_app.test_client()
    assert (
        c.post(
            "/api/0/buckets/window",
            json={"client": "c", "type": "t", "hostname": "host"},
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/0/devices/local/buckets/window",
            json={"client": "c", "type": "t", "hostname": "host"},
        ).status_code
        == 304
    )


def test_catalogue_internal_error_is_not_hidden_as_local_only(device_app, monkeypatch):
    def broken():
        raise AttributeError("catalogue failure")

    monkeypatch.setattr(device_app.api.db.storage_strategy, "device_buckets", broken)
    assert device_app.test_client().get("/api/0/devices/buckets").status_code == 500


def test_grouped_import_unsupported_backend_returns_501():
    c = AWFlask("127.0.0.1", testing=True, cors_origins=[]).test_client()
    assert (
        c.post(
            "/api/0/devices/import", json={"devices": {"peer": {"buckets": {}}}}
        ).status_code
        == 501
    )


def test_malformed_later_event_writes_no_groups(device_app):
    c = device_app.test_client()
    bucket = {
        "id": "history",
        "device_id": "first",
        "client": "c",
        "type": "t",
        "hostname": "host",
        "created": "2024-01-01T00:00:00Z",
        "events": [event("ok")],
    }
    import copy

    other = copy.deepcopy(bucket)
    other["device_id"] = "second"
    other["events"][0]["data"] = ["not an object"]
    envelope = {
        "devices": {
            "first": {"buckets": {"history": bucket}},
            "second": {"buckets": {"history": other}},
        }
    }
    assert c.post("/api/0/devices/import", json=envelope).status_code == 400
    assert c.get("/api/0/devices/first/buckets/").json == {}


def test_grouped_export_streams_events_without_bulk_read(device_app, monkeypatch):
    c = device_app.test_client()
    assert create(c, "local").status_code == 200
    assert (
        c.post(
            "/api/0/devices/local/buckets/window/events", json=event("streamed")
        ).status_code
        == 200
    )

    def bulk_read_forbidden(*args, **kwargs):
        raise AssertionError("Grouped export must not materialize all event rows")

    monkeypatch.setattr(
        device_app.api.db.storage_strategy.__class__, "get_events", bulk_read_forbidden
    )
    response = c.get("/api/0/devices/export")
    assert response.status_code == 200
    assert response.json["devices"]["server-uuid"]["buckets"]["window"]["events"][0][
        "data"
    ] == {"label": "streamed"}


def test_grouped_export_stages_before_success_and_closes_snapshot(
    device_app, monkeypatch
):
    c = device_app.test_client()
    assert create(c, "local").status_code == 200

    def broken_events(*args, **kwargs):
        yield event("partial")
        raise RuntimeError("read failed")

    monkeypatch.setattr(
        device_app.api.db.storage_strategy.__class__, "iter_events", broken_events
    )
    response = c.get("/api/0/devices/export")
    assert response.status_code == 500
    assert not device_app.api.db.storage_strategy.conn.in_transaction
    # A failed staging operation must release the writer lock too.
    assert create(c, "local", "after_failure").status_code == 200


def test_export_keeps_one_snapshot_across_bucket_iterators(device_app):
    import sqlite3
    import json

    api = device_app.api
    storage = api.db.storage_strategy
    path = storage.conn.execute("PRAGMA database_list").fetchone()[2]
    storage.conn.execute("PRAGMA journal_mode=WAL")
    for bid in ("a", "b"):
        api.for_device("local").create_bucket(bid, "t", "c", "h")
    original = storage.__class__.iter_events
    changed = []

    def events_with_concurrent_write(scoped, bid, **kwargs):
        if not changed:
            writer = sqlite3.connect(path)
            row = writer.execute("SELECT rowid FROM buckets WHERE id='b'").fetchone()[0]
            writer.execute(
                "INSERT INTO events(bucketrow,starttime,endtime,datastr) VALUES (?, ?, ?, ?)",
                (row, 1704110400000000, 1704110401000000, "{}"),
            )
            writer.commit()
            writer.close()
            changed.append(True)
        yield from original(scoped, bid, **kwargs)

    from unittest.mock import patch

    with patch.object(storage.__class__, "iter_events", events_with_concurrent_write):
        with api.stage_device_export() as staged:
            exported = json.load(staged)
    assert exported["devices"]["server-uuid"]["buckets"]["b"]["events"] == []
    assert api.for_device("local").get_eventcount("b") == 1
