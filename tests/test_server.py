import random
from datetime import datetime, timedelta
from contextlib import contextmanager


# Disabled since the web UI is no longer built in CI
# def test_index(client, benchmark):
#     def get_index():
#         assert client.get('/index.html').status_code == 200
#     benchmark(get_index)


@contextmanager
def _testing_bucket(client):
    "Context manager for creating and deleting a testing bucket"
    try:
        r = client.post('/api/0/buckets/test', json={'client': 'test', 'type': 'test', 'hostname': 'test'})
        assert r.status_code == 200
        yield
    finally:
        r = client.delete('/api/0/buckets/test')
        assert r.status_code == 200


def test_buckets(client, benchmark):
    with _testing_bucket(client):
        @benchmark
        def list_buckets():
            r = client.get('/api/0/buckets/')
            assert r.status_code == 200
            assert len(r.json) == 1


def test_heartbeats(client, benchmark):
    # FIXME: Currently tests using the memory storage method
    # TODO: Test with a longer data section and see if there's a significant difference
    # TODO: Test with a larger bucket and see if there's a significant difference
    with _testing_bucket(client):
        @benchmark
        def heartbeat():
            now = datetime.now()
            r = client.post('/api/0/buckets/test/heartbeat?pulsetime=1', json={'timestamp': now, 'duration': 0, 'data': {'random': random.random()}})
            assert r.status_code == 200


def test_get_events(client, benchmark):
    with _testing_bucket(client):
        n_events = 100
        for i in range(n_events):
            now = datetime.now() - timedelta(1)
            r = client.post('/api/0/buckets/test/heartbeat?pulsetime=0', json={'timestamp': now, 'duration': 0, 'data': {'random': random.random()}})
            assert r.status_code == 200

        @benchmark
        def get_events():
            r = client.get('/api/0/buckets/test/events?limit=-1')
            assert r.status_code == 200
            assert r.json
            assert len(r.json) == n_events


# TODO: Add benchmark for basic AFK-filtering query
