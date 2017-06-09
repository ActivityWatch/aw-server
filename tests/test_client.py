import logging
from datetime import datetime, timezone
import random

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
def queued_bucket(client):
    client.connect()
    yield
    client.disconnect()


def test_get_info(client):
    info = client.get_info()
    assert info['testing']


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


if __name__ == "__main__":
    pytest.main()
