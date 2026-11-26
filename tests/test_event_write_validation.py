"""Storage input rejections use the same HTTP contract as invalid event JSON."""

import pytest

from aw_datastore.storages import PeeweeStorage
from aw_server.server import AWFlask


@pytest.fixture
def application(tmp_path):
    def storage(testing):
        return PeeweeStorage(testing=testing, filepath=str(tmp_path / "events.db"))

    app = AWFlask("127.0.0.1", testing=True, storage_method=storage)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.api.create_bucket("test", "test", "pytest", "fixture")
    yield app
    app.api.db.storage_strategy.db.close()


@pytest.mark.parametrize("batch", [False, True])
def test_event_write_value_error_returns_bad_request(application, monkeypatch, batch):
    # Storage owns ID policy; this boundary also works with released aw-core.
    def reject(*args):
        raise ValueError("Event ID 123 belongs to another bucket")

    monkeypatch.setattr(application.api.db.storage_strategy, "insert_one", reject)
    event = {"id": 123, "timestamp": "2026-01-01T00:00:00Z", "duration": 5, "data": {}}
    response = application.test_client().post(
        "/api/0/buckets/test/events", json=[event] if batch else event
    )
    assert response.status_code == 400
    assert "another bucket" in response.get_json()["message"]


def test_heartbeat_value_error_returns_bad_request(application, monkeypatch):
    def reject(*args):
        raise ValueError("Event ID 123 belongs to another bucket")

    client = application.test_client()
    url = "/api/0/buckets/test/heartbeat?pulsetime=1"
    event = {"timestamp": "2026-01-01T00:00:00Z", "duration": 0, "data": {}}
    with monkeypatch.context() as patch:
        patch.setattr(application.api.db.storage_strategy, "insert_one", reject)
        response = client.post(url, json=dict(event, id=123))
    assert response.status_code == 400
    assert "another bucket" in response.get_json()["message"]
    # The shared heartbeat lock must have been released by the rejected request.
    assert client.post(url, json=event).status_code == 200


def test_bulk_event_write_value_error_returns_bad_request(application, monkeypatch):
    def reject(*args):
        raise ValueError("Event ID 123 belongs to another bucket")

    monkeypatch.setattr(application.api.db.storage_strategy, "insert_many", reject)
    event = {"timestamp": "2026-01-01T00:00:00Z", "duration": 5, "data": {}}
    response = application.test_client().post(
        "/api/0/buckets/test/events", json=[event, dict(event, id=123)]
    )
    assert response.status_code == 400
    assert "another bucket" in response.get_json()["message"]


def test_unexpected_storage_failure_is_still_server_error(application, monkeypatch):
    def fail(*args):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(application.api.db.storage_strategy, "insert_one", fail)
    response = application.test_client().post(
        "/api/0/buckets/test/events",
        json={"timestamp": "2026-01-01T00:00:00Z", "duration": 5, "data": {}},
    )
    assert response.status_code == 500
