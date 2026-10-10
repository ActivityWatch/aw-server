"""
CSV export of a bucket's events, matching aw-server-rust's
``GET /api/0/buckets/<id>/export/csv`` (aw-server-rust#722) so aw-webui can
use the same endpoint against either server.

Columns are ``id``, ``timestamp``, ``duration``, then the union of data keys
across all exported events (first-seen order); a data key that collides with
an earlier column name gets a ``data.`` prefix. Above ``MAX_CSV_DATA_COLUMNS``
keys, a single ``data`` column holds each event's data as JSON instead.
"""

import json
from datetime import timedelta, timezone
from typing import Any, Dict, Iterable, Iterator, List

from aw_core.models import Event

MAX_CSV_DATA_COLUMNS = 32

# Spreadsheets trim these before deciding whether a cell is a formula.
_FORMULA_LEADING_WHITESPACE = " \t\r\n"
_FORMULA_STARTERS = ("=", "+", "-", "@")


def _neutralize_formula(s: str) -> str:
    if s.lstrip(_FORMULA_LEADING_WHITESPACE).startswith(_FORMULA_STARTERS):
        return "'" + s
    return s


def _csv_escape(s: str) -> str:
    s = _neutralize_formula(s)
    if any(c in s for c in ',"\n\r'):
        return '"' + s.replace('"', '""') + '"'
    return s


def _csv_record(fields: Iterable[str]) -> str:
    # RFC-4180: CRLF record delimiter
    return ",".join(_csv_escape(f) for f in fields) + "\r\n"


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _duration(duration: timedelta) -> str:
    """Seconds with nine decimals, like aw-server-rust (exact to the microsecond)."""
    sign = "-" if duration < timedelta(0) else ""
    us = abs(duration) // timedelta(microseconds=1)
    return f"{sign}{us // 1_000_000}.{(us % 1_000_000) * 1000:09d}"


_MISSING = object()


def _field(value: Any) -> str:
    # A key missing from the event is an empty cell; a present null is "null"
    if value is _MISSING:
        return ""
    if isinstance(value, str):
        return value
    return _json(value)


def _header_names(data_keys: List[str]) -> List[str]:
    """``id``, ``timestamp``, ``duration``, then one name per data key.

    A data key that would repeat an earlier header name (e.g. a data key
    ``duration``) is prefixed with ``data.`` until unique, like aw-server-rust.
    Only the header changes; values are still read by the original key.
    """
    names = ["id", "timestamp", "duration"]
    used = set(names)
    for key in data_keys:
        name = key
        while name in used:
            name = "data." + name
        used.add(name)
        names.append(name)
    return names


def events_to_csv(events: List[Event]) -> Iterator[str]:
    """Yield CSV records for events, in the order given."""
    keys: Dict[str, None] = {}
    for e in events:
        for k in e.data:
            keys.setdefault(k)
    data_keys = list(keys)
    data_json_column = len(data_keys) > MAX_CSV_DATA_COLUMNS
    if data_json_column:
        data_keys = ["data"]

    yield _csv_record(_header_names(data_keys))
    for e in events:
        fields = [
            "" if e.id is None else str(e.id),
            e.timestamp.astimezone(timezone.utc).isoformat(),
            _duration(e.duration),
        ]
        if data_json_column:
            fields.append(_json(e.data))
        else:
            fields.extend(_field(e.data.get(k, _MISSING)) for k in data_keys)
        yield _csv_record(fields)


def content_disposition(filename: str) -> str:
    """Quoted attachment filename with header-breaking characters replaced."""
    safe = "".join(
        "_" if (ord(c) < 32 or 127 <= ord(c) < 160 or c in '"\\;') else c
        for c in filename
    )
    return f'attachment; filename="{safe}"'
