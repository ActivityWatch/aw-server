import logging
from datetime import datetime, timezone, timedelta
import random
from time import sleep

import pytest

from aw_client import ActivityWatchClient
from aw_core.models import Event

logging.basicConfig(level=logging.WARN)


@pytest.fixture(scope="session")
def client():
    yield ActivityWatchClient("unittest", testing=True)


@pytest.fixture(scope="function")
def bucket(client):
    bucket_id = "test-" + str(random.randint(0, 10**5))
    event_type = "testevents"
    client.create_bucket(bucket_id, event_type)
    yield bucket_id
    client.delete_bucket(bucket_id)


@pytest.fixture
def queued_bucket(client, bucket):
    client.connect()
    yield bucket
    client.disconnect()


def test_get_info(client):
    info = client.get_info()
    assert info['testing']


def _create_heartbeat_events():
    e1_ts = datetime.now(tz=timezone.utc)
    e2_ts = e1_ts + timedelta(seconds=9)

    # Needed since server (or underlying datastore) drops precision up to milliseconds.
    # Update: Even with millisecond precision it sometimes fails. (tried using `round` and `int`)
    #         Now rounding down to 10ms precision to prevent random failure.
    #         10ms precision at least seems to work well.
    # TODO: Figure out why it sometimes fails with millisecond precision.
    e1_ts = e1_ts.replace(microsecond=int(e1_ts.microsecond / 10000) * 100)
    e2_ts = e2_ts.replace(microsecond=int(e2_ts.microsecond / 10000) * 100)

    e1 = Event(timestamp=e1_ts, data={"label": "test"})
    e2 = Event(timestamp=e2_ts, data={"label": "test"})

    return e1, e2


def _create_periodic_events(num_events, start=datetime.now(tz=timezone.utc),
                            delta=timedelta(hours=1)):
    num_events = 1000
    events = num_events * [None]

    for i, dt in ((i, start + i * delta) for i in range(len(events))):
        events[i] = Event(timestamp=dt, data={"label": "test"})

    return events


def test_heartbeat(client, bucket):
    bucket_id = bucket

    e1, e2 = _create_heartbeat_events()

    client.heartbeat(bucket_id, e1, pulsetime=0)
    client.heartbeat(bucket_id, e2, pulsetime=10)
    event = client.get_events(bucket_id, limit=1)[0]

    assert event.timestamp == e1.timestamp
    assert event.duration == e2.timestamp - e1.timestamp


def test_queued_heartbeat(client, queued_bucket):
    bucket_id = queued_bucket

    e1, e2 = _create_heartbeat_events()

    client.heartbeat(bucket_id, e1, pulsetime=0, queued=True)
    client.heartbeat(bucket_id, e2, pulsetime=10, queued=True)
    # Needed since the dispatcher thread might introduce some delay
    sleep(1)
    event = client.get_events(bucket_id, limit=1)[0]

    assert event.timestamp == e1.timestamp
    assert event.duration == e2.timestamp - e1.timestamp


def test_list_buckets(client, bucket):
    buckets = client.get_buckets()
    print(buckets.keys())
    assert bucket in buckets.keys()


def test_send_event(client, bucket):
    event = Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test"})
    client.send_event(bucket, event)
    recv_events = client.get_events(bucket)
    assert [event] == recv_events


def test_send_events(client, bucket):
    events = [
        Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test"}),
        Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test2"}),
    ]
    client.send_events(bucket, events)
    recv_events = client.get_events(bucket)
    assert events == sorted(recv_events, reverse=True, key=lambda e: e.timestamp)


def test_get_events_interval(client, bucket):
    start_dt = datetime.now(tz=timezone.utc)
    delta = timedelta(hours=1)
    events = _create_periodic_events(1000, delta=delta, start=start_dt)

    client.send_events(bucket, events)

    # start kwarg doesn't seem to be range-inclusive
    recv_events = client.get_events(bucket, limit=50, start=start_dt, end=start_dt + timedelta(days=1))

    assert len(recv_events) == 24
    assert recv_events == sorted(events[1:25], reverse=True, key=lambda e: e.timestamp)


def test_store_many_events(client, bucket):
    events = _create_periodic_events(1000)

    client.send_events(bucket, events)
    recv_events = client.get_events(bucket, limit=-1)

    assert len(events) == len(recv_events)
    assert recv_events == sorted(events, reverse=True, key=lambda e: e.timestamp)


if __name__ == "__main__":
    pytest.main()
