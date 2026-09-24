"""Exercise real SQLite locks across separate request-thread connections."""
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pytest
from aw_datastore.storages.peewee import PeeweeStorage

from aw_server.server import AWFlask


@pytest.fixture()
def sqlite_app(tmp_path):
    app = AWFlask(
        "127.0.0.1",
        testing=True,
        storage_method=partial(PeeweeStorage, filepath=str(tmp_path / "events.db")),
        cors_origins=[],
    )
    database = app.api.db.storage_strategy.db
    with app.test_client() as client:
        response = client.post(
            "/api/0/buckets/test",
            json={"client": "test", "type": "test", "hostname": "test"},
        )
        assert response.status_code == 200
    try:
        yield app, database
    finally:
        database.close()


def request_in_thread(app, database, method, path, **kwargs):
    # Keep failures fast on rollback-journal SQLite, rather than waiting for
    # its default busy timeout while the main thread holds a transaction.
    database.connect(reuse_if_open=True)
    database.execute_sql("PRAGMA busy_timeout = 100")
    try:
        response = getattr(app.test_client(), method)(path, **kwargs)
        return response.status_code, response.get_json(), database.is_closed()
    finally:
        database.close()


def test_read_during_write(sqlite_app):
    app, database = sqlite_app
    with ThreadPoolExecutor(max_workers=1) as executor:
        with database.atomic("EXCLUSIVE"):
            database.execute_sql("UPDATE bucketmodel SET name = 'pending'")
            future = executor.submit(
                request_in_thread, app, database, "get", "/api/0/buckets/test/events"
            )
            status, events, closed = future.result(timeout=5)
            assert status == 200
            assert events == []
            assert closed


def test_write_during_read(sqlite_app):
    app, database = sqlite_app
    with ThreadPoolExecutor(max_workers=1) as executor:
        with database.atomic():
            # Retain a read snapshot until the concurrent writer has committed.
            database.execute_sql("SELECT * FROM bucketmodel").fetchall()
            future = executor.submit(
                request_in_thread,
                app,
                database,
                "post",
                "/api/0/buckets/test/events",
                json=[{"timestamp": "2024-01-01T00:00:00Z", "duration": 1, "data": {}}],
            )
            status, events, closed = future.result(timeout=5)
            assert status == 200
            assert len(events) == 1
            assert closed
    response = app.test_client().get("/api/0/buckets/test/events")
    assert len(response.get_json()) == 1


def test_connection_closed_after_error(sqlite_app, monkeypatch):
    app, database = sqlite_app

    def database_error(*args, **kwargs):
        database.execute_sql("SELECT * FROM bucketmodel").fetchall()
        raise RuntimeError("request failed")

    monkeypatch.setattr(app.api, "get_events", database_error)
    with ThreadPoolExecutor(max_workers=1) as executor:
        status, _, closed = executor.submit(
            request_in_thread, app, database, "get", "/api/0/buckets/test/events"
        ).result(timeout=5)
    assert status == 500
    assert closed
