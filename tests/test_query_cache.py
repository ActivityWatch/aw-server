from datetime import datetime, timedelta, timezone

import aw_datastore
import pytest
from aw_core.models import Event
from aw_datastore import Datastore
from aw_datastore.storages import SqliteStorage

from aw_server.api import ServerAPI
from aw_server.query_cache import QueryCache, coalesce

UTC = timezone.utc
DAY1 = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC))
DAY2 = (datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC))


def tp(period) -> str:
    return f"{period[0].isoformat()}/{period[1].isoformat()}"


# --- QueryCache unit tests ---


def test_put_get_and_overlap_invalidation():
    c = QueryCache()
    k1, k2 = c.key("q", DAY1), c.key("q", DAY2)
    assert c.put(k1, DAY1, [1], c.generation())
    assert c.put(k2, DAY2, [2], c.generation())
    assert c.get(k1) == [1]

    c.invalidate([(DAY1[0] + timedelta(hours=3), DAY1[0] + timedelta(hours=4))])
    assert c.get(k1) is None
    assert c.get(k2) == [2]  # non-overlapping write keeps it


def test_key_normalizes_timezone_not_query_text():
    cet = timezone(timedelta(hours=1))
    same_period = (DAY1[0].astimezone(cet), DAY1[1].astimezone(cet))
    assert QueryCache.key("a;", DAY1) == QueryCache.key("a;", same_period)
    assert QueryCache.key("a;", DAY1) != QueryCache.key("b;", DAY1)
    # whitespace inside string literals is significant
    assert QueryCache.key('RETURN = "a\n b";', DAY1) != QueryCache.key(
        'RETURN = "a\nb";', DAY1
    )


def test_put_refused_after_overlapping_write_during_computation():
    c = QueryCache()
    started = c.generation()
    c.invalidate([(DAY1[0], DAY1[0] + timedelta(minutes=1))])  # write mid-query
    assert not c.put(c.key("q", DAY1), DAY1, [1], started)
    # a write elsewhere doesn't block storing (boundaries count as overlap, so avoid midnight)
    started = c.generation()
    c.invalidate([(DAY2[0] + timedelta(hours=1), DAY2[0] + timedelta(hours=2))])
    assert c.put(c.key("q", DAY1), DAY1, [1], started)


def test_put_refused_when_write_log_overflowed():
    c = QueryCache(write_log_size=2)
    started = c.generation()
    for i in range(3):  # non-overlapping, but the log no longer reaches `started`
        c.invalidate([(DAY2[0], DAY2[0] + timedelta(seconds=i))])
    assert not c.put(c.key("q", DAY1), DAY1, [1], started)


def test_coalesce_bulk_write_ranges():
    h = lambda n: DAY1[0] + timedelta(hours=n)  # noqa: E731
    assert coalesce([(h(3), h(4)), (h(1), h(2)), (h(2), h(3))]) == [(h(1), h(4))]
    assert coalesce([(h(1), h(2)), (h(5), h(6))]) == [(h(1), h(2)), (h(5), h(6))]
    many = [(h(i), h(i) + timedelta(minutes=1)) for i in range(0, 200, 2)]
    assert coalesce(many, max_ranges=64) == [(h(0), h(198) + timedelta(minutes=1))]


def test_bulk_write_is_one_generation():
    c = QueryCache(write_log_size=2)
    started = c.generation()
    c.invalidate(
        [
            (DAY2[0] + timedelta(hours=i), DAY2[0] + timedelta(hours=i, minutes=1))
            for i in range(1, 10)
        ]
    )
    assert c.generation() == started + 1
    assert c.put(c.key("q", DAY1), DAY1, [1], started)


def test_cacheable_margin():
    c = QueryCache(margin=timedelta(minutes=10))
    now = datetime(2024, 1, 2, 12, tzinfo=UTC)
    assert c.cacheable(DAY1, now=now)
    assert not c.cacheable(
        (now - timedelta(hours=1), now - timedelta(minutes=5)), now=now
    )
    assert not c.cacheable((now, now + timedelta(days=1)), now=now)


def test_lru_bounds():
    c = QueryCache(max_entries=2)
    keys = [c.key(str(i), DAY1) for i in range(3)]
    for k in keys:
        c.put(k, DAY1, [0], c.generation())
    assert c.get(keys[0]) is None
    assert c.get(keys[2]) == [0]
    assert c.stats()["entries"] == 2


def test_clear_blocks_inflight_store():
    c = QueryCache()
    started = c.generation()
    c.clear()
    assert not c.put(c.key("q", DAY1), DAY1, [1], started)


# --- ServerAPI integration (in-memory datastore) ---

BUCKET = "test-cache-bucket"


@pytest.fixture()
def api():
    db = Datastore(aw_datastore.get_storage_methods()["memory"], testing=True)
    a = ServerAPI(db=db, testing=True)
    a.create_bucket(BUCKET, "test", "test", "testhost")
    a.create_events(
        BUCKET,
        [Event(timestamp=DAY1[0] + timedelta(hours=1), duration=60, data={"a": 1})],
    )
    return a


def total(api, period=DAY1, cache=True) -> float:
    q = [f'events = query_bucket("{BUCKET}");', "RETURN = sum_durations(events);"]
    return api.query2("test", q, [tp(period)], cache)[0].total_seconds()


def test_repeat_query_hits_cache(api):
    assert total(api) == 60
    assert total(api) == 60
    assert api.query_cache.stats()["hits"] == 1


def test_heartbeat_overlapping_cached_period_invalidates(api):
    assert total(api) == 60
    # a late heartbeat merging into the day's last event
    hb = Event(
        timestamp=DAY1[0] + timedelta(hours=1, seconds=90), duration=0, data={"a": 1}
    )
    api.heartbeat(BUCKET, hb, pulsetime=60)
    assert total(api) == 90


def test_merge_after_out_of_order_heartbeat_invalidates_replaced_event(api):
    # Memory storage does not set an id on the event passed to insert(), so the
    # heartbeat falls back to replace_last(): this covers that path, where the
    # stored (DAY2) last event is overwritten and its cached result must drop.
    b = "ooo-bucket"
    api.create_bucket(b, "test", "test", "testhost")
    q = [f'events = query_bucket("{b}");', "RETURN = sum_durations(events);"]

    def day2_total():
        return api.query2("t", q, [tp(DAY2)], True)[0].total_seconds()

    # newer event on DAY2, then an older heartbeat on DAY1 with other data
    api.heartbeat(
        b, Event(timestamp=DAY2[0] + timedelta(hours=5), duration=30, data={"x": 1}), 0
    )
    api.heartbeat(
        b, Event(timestamp=DAY1[0] + timedelta(hours=5), duration=0, data={"y": 1}), 0
    )
    assert day2_total() == 30
    # a matching heartbeat merges and replace_last() overwrites the stored
    # (DAY2) last event: its cached DAY2 result must be dropped
    api.heartbeat(
        b,
        Event(
            timestamp=DAY1[0] + timedelta(hours=5, seconds=10),
            duration=0,
            data={"y": 1},
        ),
        60,
    )
    assert day2_total() == api.query2("t", q, [tp(DAY2)], False)[0].total_seconds()


def test_merge_out_of_order_by_id_preserves_newer_event_and_invalidates_merged(
    tmp_path,
):
    # SQLite storage sets an id on the inserted event, so the merge is written
    # back with replace(id, merged): the merged event's cached period must be
    # dropped, while the newer stored event stays intact.
    db = Datastore(SqliteStorage, testing=True, filepath=str(tmp_path / "test.db"))
    a = ServerAPI(db=db, testing=True)
    b = "ooo-id-bucket"
    a.create_bucket(b, "test", "test", "testhost")
    q = [f'events = query_bucket("{b}");', "RETURN = sum_durations(events);"]

    def day_total(day, cache=True):
        return a.query2("t", q, [tp(day)], cache)[0].total_seconds()

    a.heartbeat(
        b, Event(timestamp=DAY2[0] + timedelta(hours=5), duration=30, data={"x": 1}), 0
    )
    a.heartbeat(
        b, Event(timestamp=DAY1[0] + timedelta(hours=5), duration=0, data={"y": 1}), 0
    )
    assert day_total(DAY1) == 0
    assert day_total(DAY2) == 30
    a.heartbeat(
        b,
        Event(
            timestamp=DAY1[0] + timedelta(hours=5, seconds=10),
            duration=0,
            data={"y": 1},
        ),
        60,
    )
    # merged DAY1 event changed: its cached result must be re-queried
    assert day_total(DAY1) == 10
    assert day_total(DAY1) == day_total(DAY1, cache=False)
    # newer DAY2 event untouched: its cached result is unchanged and still valid
    assert day_total(DAY2) == 30
    assert day_total(DAY2) == day_total(DAY2, cache=False)


def test_insert_and_delete_invalidate_only_overlapping(api):
    assert total(api) == 60
    assert total(api, DAY2) == 0
    [ev] = api.create_events(
        BUCKET, [Event(timestamp=DAY2[0] + timedelta(hours=2), duration=30, data={})]
    )
    assert total(api) == 60  # DAY1 untouched: still served from cache
    assert api.query_cache.stats()["hits"] == 1
    assert total(api, DAY2) == 30
    api.delete_event(BUCKET, ev.id)
    assert total(api, DAY2) == 0


def test_replacing_event_by_id_invalidates_old_range(api):
    [ev] = api.create_events(
        BUCKET, [Event(timestamp=DAY2[0] + timedelta(hours=2), duration=30, data={})]
    )
    assert total(api, DAY2) == 30
    # move the event to DAY1 by re-inserting with the same id
    api.create_events(
        BUCKET,
        [Event(id=ev.id, timestamp=DAY1[0] + timedelta(hours=5), duration=30, data={})],
    )
    assert total(api, DAY2) == 0
    assert total(api) == 90


def test_bucket_changes_clear_cache(api):
    q = ['RETURN = find_bucket("other-bucket");']
    with pytest.raises(Exception):
        api.query2("test", q, [tp(DAY1)], True)
    api.create_bucket("other-bucket", "test", "test", "testhost")
    assert api.query2("test", q, [tp(DAY1)], True) == ["other-bucket"]
    assert total(api) == 60
    api.delete_bucket("other-bucket")
    assert api.query_cache.stats()["entries"] == 0


def test_current_and_future_periods_not_cached(api):
    now = datetime.now(UTC)
    total(api, (now - timedelta(hours=1), now))
    total(api, (now, now + timedelta(days=1)))
    assert api.query_cache.stats()["entries"] == 0


def test_cache_opt_out(api):
    assert total(api, cache=False) == 60
    assert total(api, cache=False) == 60
    assert api.query_cache.stats() == {"entries": 0, "bytes": 0, "hits": 0, "misses": 0}


def test_cache_disabled_by_config():
    db = Datastore(aw_datastore.get_storage_methods()["memory"], testing=True)
    a = ServerAPI(db=db, testing=True, query_cache=False)
    a.create_bucket(BUCKET, "test", "test", "testhost")
    assert total(a) == 0


def test_rest_cache_flag(flask_client):
    body = {"query": ["RETURN = 424242;"], "timeperiods": [tp(DAY1)]}
    stats = flask_client.application.api.query_cache.stats
    before = stats()["entries"]
    assert flask_client.post("/api/0/query/?cache=false", json=body).status_code == 200
    assert (
        flask_client.post("/api/0/query/", json={**body, "cache": False}).status_code
        == 200
    )
    assert stats()["entries"] == before
    assert flask_client.post("/api/0/query/", json=body).json == [424242]
    assert stats()["entries"] == before + 1
