import random
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def bucket(flask_client):
    "Context manager for creating and deleting a testing bucket"
    try:
        bucket_id = 'test'
        r = flask_client.post('/api/0/buckets/{}'.format(bucket_id), json={'client': 'test', 'type': 'test', 'hostname': 'test'})
        assert r.status_code == 200
        yield bucket_id
    finally:
        r = flask_client.delete('/api/0/buckets/{}'.format(bucket_id))
        assert r.status_code == 200


def test_buckets(flask_client, bucket, benchmark):
    @benchmark
    def list_buckets():
        r = flask_client.get('/api/0/buckets/')
        print(r.json)
        assert r.status_code == 200
        assert len(r.json) == 1


def test_heartbeats(flask_client, bucket, benchmark):
    # FIXME: Currently tests using the memory storage method
    # TODO: Test with a longer data section and see if there's a significant difference
    # TODO: Test with a larger bucket and see if there's a significant difference
    @benchmark
    def heartbeat():
        now = datetime.now()
        r = flask_client.post('/api/0/buckets/test/heartbeat?pulsetime=1'.format(bucket), json={'timestamp': now, 'duration': 0, 'data': {'random': random.random()}})
        assert r.status_code == 200


def test_get_events(flask_client, bucket, benchmark):
    n_events = 100
    start_time = datetime.now() - timedelta(1)
    for i in range(n_events):
        now = datetime.now() - timedelta(1)
        r = flask_client.post('/api/0/buckets/test/heartbeat?pulsetime=0'.format(bucket), json={'timestamp': now, 'duration': 0, 'data': {'random': random.random()}})
        assert r.status_code == 200

    @benchmark
    def get_events():
        r = flask_client.get('/api/0/buckets/test/events'.format(bucket))
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get('/api/0/buckets/test/events?limit=-1'.format(bucket))
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get('/api/0/buckets/test/events?limit=10'.format(bucket))
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == 10
        
        r = flask_client.get('/api/0/buckets/test/events?limit=100'.format(bucket))
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        r = flask_client.get('/api/0/buckets/test/events?limit=1000'.format(bucket))
        assert r.status_code == 200
        assert r.json
        assert len(r.json) == n_events

        
    

# TODO: Add benchmark for basic AFK-filtering query
