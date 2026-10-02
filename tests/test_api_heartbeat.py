from datetime import datetime, timedelta, timezone

import pytest
from aw_core.models import Event
from aw_datastore import Datastore
from aw_datastore.storages import PeeweeStorage

from aw_server.api import ServerAPI


@pytest.fixture()
def api(tmp_path):
    db = Datastore(PeeweeStorage, testing=True, filepath=str(tmp_path / "test.db"))
    api = ServerAPI(db=db, testing=True)
    api.create_bucket("test", event_type="test", client="test", hostname="test")
    return api


def test_heartbeat_merge_updates_the_merged_event_not_the_latest(api):
    """A merge must update the event it merged into, not whichever stored event
    happens to sort last by timestamp.

    An out-of-order heartbeat (e.g. from a watcher that restarted mid-period)
    used to make replace_last() overwrite the newer event with a copy of the
    merged one, leaving two events with the same timestamp and different
    durations. See ActivityWatch/aw-watcher-afk#61.
    """
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    api.heartbeat("test", Event(timestamp=t0 + timedelta(seconds=10), data={"a": 1}), 5)
    # Older than the stored event, different data: inserted as a new event.
    api.heartbeat("test", Event(timestamp=t0, data={"b": 1}), 5)
    # Merges into the {"b": 1} event.
    api.heartbeat("test", Event(timestamp=t0 + timedelta(seconds=2), data={"b": 1}), 5)

    events = api.get_events("test")
    assert sorted((e["timestamp"], e["duration"], e["data"]) for e in events) == [
        (t0.isoformat(), 2.0, {"b": 1}),
        ((t0 + timedelta(seconds=10)).isoformat(), 0.0, {"a": 1}),
    ]
