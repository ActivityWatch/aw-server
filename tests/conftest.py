import logging
import os

import pytest
from aw_datastore import Datastore, get_storage_methods
from aw_server.api import ServerAPI
from aw_client import ActivityWatchClient
from aw_server.server import AWFlask

logging.basicConfig(level=logging.WARN)


@pytest.fixture(autouse=True)
def _clear_aw_profile_after_test():
    """export_profile() writes os.environ directly; monkeypatch.delenv does
    not record an undo when the var was already unset, so later tests would
    inherit a leftover profile."""
    yield
    os.environ.pop("AW_PROFILE", None)


@pytest.fixture(scope="session")
def app():
    # AWFlask does not go through parse_settings(), so a leftover AW_PROFILE
    # from the environment (or a prior test) would disagree with testing=True.
    old = os.environ.pop("AW_PROFILE", None)
    application = AWFlask("127.0.0.1", testing=True)
    if old is not None:
        os.environ["AW_PROFILE"] = old
    return application


@pytest.fixture(scope="session")
def flask_client(app):
    yield app.test_client()


@pytest.fixture(scope="session")
def aw_client():
    # TODO: Could it be possible to write a sisterclass of ActivityWatchClient
    # which calls aw_server.api directly? Would it be of use? Would add another
    # layer of integration tests that are actually more like unit tests.
    c = ActivityWatchClient("aw-client-test", testing=True)
    yield c

    # Delete test buckets after all tests needing the fixture have been run
    buckets = c.get_buckets()
    for bucket_id in buckets:
        if bucket_id.startswith("test-"):
            c.delete_bucket(bucket_id)


@pytest.fixture(params=["memory", "peewee", "sqlite"])
def isolated_api(request, tmp_path, monkeypatch):
    """Exercise the storage backends without accessing a user's database/settings."""
    monkeypatch.setattr("aw_server.settings.get_config_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(
        "aw_datastore.storages.peewee.get_data_dir",
        lambda _: str(tmp_path),
    )
    storage = get_storage_methods()[request.param]
    kwargs = (
        {} if request.param == "memory" else {"filepath": str(tmp_path / "test.db")}
    )
    db = Datastore(storage, testing=True, **kwargs)
    try:
        yield ServerAPI(db, testing=True)
    finally:
        if request.param == "peewee":
            db.storage_strategy.db.close()
        elif request.param == "sqlite":
            db.storage_strategy.conn.close()
