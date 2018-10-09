import random
from datetime import datetime


def test_index(client):
    assert client.get('/index.html').status_code == 200


def test_buckets(client):
    r = client.get('/api/0/buckets/')
    assert r.status_code == 200
    print(r.data)
    print(r.json)


def test_benchmark_buckets(client, benchmark):
    def list_buckets():
        client.get('/api/0/buckets/')

    benchmark(list_buckets)


def test_benchmark_heartbeats(client, benchmark):
    # FIXME: Currently tests using the memory storage method
    # TODO: Test with a longer data section and see if there's a significant difference
    # TODO: Test with a larger bucket and see if there's a significant difference

    def heartbeat():
        now = datetime.now()
        for i in range(100):
            r = client.post('/api/0/buckets/test/heartbeat?pulsetime=1', json={'timestamp': now, 'duration': 0, 'data': {'random': random.random()}})
            assert r.status_code == 200

    # Setup bucket
    r = client.post('/api/0/buckets/test', json={'client': 'test', 'type': 'test', 'hostname': 'test'})
    assert r.status_code == 200

    benchmark(heartbeat)

    # Teardown bucket
    r = client.delete('/api/0/buckets/test')
    assert r.status_code == 200
