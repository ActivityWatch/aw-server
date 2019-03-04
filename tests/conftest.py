import logging
import random
import time

import pytest

import aw_server
from aw_client import ActivityWatchClient

logging.basicConfig(level=logging.WARN)


@pytest.fixture(scope="session")
def app():
    return aw_server.create_app(testing=True)


@pytest.fixture(scope="session")
def flask_client(app):
    yield app.test_client()


@pytest.fixture(scope="session")
def aw_client():
    # TODO: Could it be possible to write a sisterclass of ActivityWatchClient
    # which calls aw_server.api directly? Would it be of use? Would add another
    # layer of integration tests that are actually more like unit tests.
    c = ActivityWatchClient("client-test", testing=True)
    yield c

    # Delete test buckets after all tests needing the fixture have been run
    buckets = c.get_buckets()
    for bucket_id in buckets:
        if bucket_id.startswith("test-"):
            c.delete_bucket(bucket_id)


@pytest.fixture(scope="function")
def bucket(aw_client):
    bucket_id = "test-" + str(random.randint(0, 10**5))
    event_type = "testevents"
    aw_client.create_bucket(bucket_id, event_type, queued=False)
    print(f"Created bucket {bucket_id}")
    time.sleep(1)
    yield bucket_id
    aw_client.delete_bucket(bucket_id)


@pytest.fixture
def queued_bucket(aw_client, bucket):
    # FIXME: We need a way to clear the failed_requests file in order
    # to have tests behave reasonably between runs.
    aw_client.connect()
    yield bucket
    aw_client.disconnect()
