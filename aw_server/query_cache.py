"""In-memory cache for query results over finished (past) timeperiods.

Clients such as aw-webui split long views (Year, All time) into one request per
day, and every page load recomputes all of them. Past days rarely change, so we
keep their results, keyed by (query text, timeperiod).

Correctness rests on invalidation, not on "the past never changes":

- Queries only read data through the bucket list (``find_bucket``) and
  period-bounded event reads (``query_bucket``, ``query_bucket_eventcount``),
  which return events whose extent overlaps the period.
- Every write goes through ``ServerAPI``. After each write we record the time
  range it affected (the full extent of every inserted, replaced, merged or
  deleted event) and drop cached entries whose period overlaps it. Bucket
  create/update/delete/import clears the cache, since they can change what
  ``find_bucket`` resolves to.
- Race: a query that started before an overlapping write finished may have read
  old data. Each computation records the write generation it started at, and
  ``put`` refuses to store if any overlapping write happened since (or if the
  write log no longer reaches back that far).

Only periods that ended at least ``margin`` ago are cached, so today and the
current hour are always computed fresh. The cache is in-memory only: a restart
starts empty, which also covers any write that bypassed the API (e.g. editing
the database file directly while the server was stopped).
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MIN = datetime.min.replace(tzinfo=timezone.utc)
_MAX = datetime.max.replace(tzinfo=timezone.utc)

TimeRange = Tuple[datetime, datetime]


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def event_range(event: Any) -> TimeRange:
    """Full extent of an event, as the datastore's overlap check sees it."""
    start = _utc(event.timestamp)
    return start, start + event.duration


def _overlaps(a: TimeRange, b: TimeRange) -> bool:
    # Inclusive on both ends: conservative (may invalidate a touching period).
    return a[0] <= b[1] and b[0] <= a[1]


def coalesce(ranges: Iterable[TimeRange], max_ranges: int = 64) -> List[TimeRange]:
    """Merge overlapping/touching ranges. Past ``max_ranges``, fall back to one
    bounding range: over-invalidating after a big import is fine, scanning the
    cache once per imported event is not."""
    merged: List[TimeRange] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    if len(merged) > max_ranges:
        return [(merged[0][0], max(end for _, end in merged))]
    return merged


class QueryCache:
    def __init__(
        self,
        max_entries: int = 10000,
        max_bytes: int = 128 * 1024 * 1024,
        margin: timedelta = timedelta(minutes=10),
        write_log_size: int = 10000,
    ) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.margin = margin
        self._lock = threading.Lock()
        # key -> (period, result, size)
        self._entries: "OrderedDict[str, Tuple[TimeRange, Any, int]]" = OrderedDict()
        self._bytes = 0
        self._gen = 0
        # (generation, affected ranges) of recent writes, oldest first
        self._writes: Deque[Tuple[int, List[TimeRange]]] = deque(maxlen=write_log_size)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(query: str, period: TimeRange) -> str:
        # Exact query text: whitespace can be significant inside string literals.
        raw = json.dumps(
            [query, _utc(period[0]).isoformat(), _utc(period[1]).isoformat()]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def cacheable(self, period: TimeRange, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return _utc(period[1]) <= now - self.margin

    def generation(self) -> int:
        with self._lock:
            return self._gen

    def get(self, key: str) -> Optional[Any]:
        """Return the cached result. It is shared, not copied: callers must not
        mutate it (the REST layer only serializes it; a deepcopy per hit would
        roughly double warm load times)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry[1]

    def put(self, key: str, period: TimeRange, result: Any, started_gen: int) -> bool:
        """Store ``result`` unless a write overlapping ``period`` happened after ``started_gen``."""
        period = (_utc(period[0]), _utc(period[1]))
        try:
            size = len(json.dumps(result, default=str))
        except (TypeError, ValueError):
            return False
        if size > self.max_bytes:
            return False
        with self._lock:
            if self._gen != started_gen:
                oldest_logged = self._writes[0][0] if self._writes else self._gen + 1
                if oldest_logged > started_gen + 1:
                    return False  # write log doesn't reach back far enough to tell
                for gen, affected in self._writes:
                    if gen > started_gen and any(
                        _overlaps(r, period) for r in affected
                    ):
                        return False
            old = self._entries.pop(key, None)
            if old:
                self._bytes -= old[2]
            self._entries[key] = (period, result, size)
            self._bytes += size
            while self._entries and (
                len(self._entries) > self.max_entries or self._bytes > self.max_bytes
            ):
                _, (_, _, evicted_size) = self._entries.popitem(last=False)
                self._bytes -= evicted_size
            return True

    def invalidate(self, ranges: Iterable[TimeRange]) -> None:
        """Record writes affecting ``ranges`` and drop overlapping entries. Call after the write."""
        ranges = coalesce((_utc(a), _utc(b)) for a, b in ranges)
        if not ranges:
            return
        with self._lock:
            # one generation per write call, however many events it touched
            self._gen += 1
            self._writes.append((self._gen, ranges))
            stale = [
                k
                for k, (period, _, _) in self._entries.items()
                if any(_overlaps(r, period) for r in ranges)
            ]
            for k in stale:
                self._bytes -= self._entries.pop(k)[2]
        if stale:
            logger.debug("query cache: invalidated %d entries", len(stale))

    def clear(self) -> None:
        """Drop everything (bucket list changed). Also blocks in-flight stores."""
        self.invalidate([(_MIN, _MAX)])
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._entries),
                "bytes": self._bytes,
                "hits": self.hits,
                "misses": self.misses,
            }
