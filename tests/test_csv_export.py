"""CSV export must remain readable for previously accepted non-object data."""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from aw_core.models import Event
from aw_server.csv_export import MAX_CSV_DATA_COLUMNS, events_to_csv
from aw_server.server import AWFlask


@pytest.mark.parametrize("legacy_data", [["x"], "legacy", 5, 1.5, True])
def test_legacy_nonobject_csv_stream_roundtrip(legacy_data):
    app = AWFlask("127.0.0.1", testing=True)
    client = app.test_client()
    bucket = "test-legacy-csv"
    response = client.post(
        f"/api/0/buckets/{bucket}",
        json={"client": "test", "type": "test", "hostname": "test"},
    )
    assert response.status_code == 200
    payloads = [{"title": "=SUM(A1:A2)", "unicode": 'å\n"'}, legacy_data]
    for index, data in enumerate(payloads):
        response = client.post(
            f"/api/0/buckets/{bucket}/events",
            json={
                "timestamp": f"2026-01-01T00:00:0{index}Z",
                "duration": 1.25,
                "data": data,
            },
        )
        assert response.status_code == 200

    # Headers alone cannot detect exceptions in the streamed body.
    response = client.get(f"/api/0/buckets/{bucket}/export/csv")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0] == ["id", "timestamp", "duration", "data"]
    assert len(rows) == 3
    assert [json.loads(row[3]) for row in rows[1:]] == payloads[::-1]
    assert [row[2] for row in rows[1:]] == ["1.250000000"] * 2
    assert [row[1] for row in rows[1:]] == [
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:00+00:00",
    ]
    # Exporting must not rewrite the stored payloads.
    stored = client.get(f"/api/0/buckets/{bucket}/events").get_json()
    assert [event["data"] for event in stored] == payloads[::-1]


@pytest.mark.parametrize("data", [[], False, 0, ""])
def test_legacy_nonobject_csv_falsey_data_preserved(data):
    # aw-core's constructor normalizes falsey data to {}. Seed historical
    # values explicitly to test the exporter boundary without changing ingest.
    event = Event(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    event.data = data
    rows = list(csv.reader(events_to_csv([event])))
    assert rows[0] == ["id", "timestamp", "duration", "data"]
    assert json.loads(rows[1][3]) == data


def test_legacy_nonobject_csv_null_uses_model_semantics():
    event = Event(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), data=None)
    assert event.data == {}
    event.data = None
    assert event.data == {}  # The property also normalizes an explicitly stored null.
    rows = list(csv.reader(events_to_csv([event])))
    assert rows[0] == ["id", "timestamp", "duration"]
    assert len(rows[1]) == 3


def test_legacy_nonobject_csv_object_only_compatibility():
    event = Event(
        id=7,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
        duration=timedelta(microseconds=1234567),
        data={
            "id": "=1+1",
            "data.id": " @command",
            "title": 'å,"line\nnext',
            "null": None,
            "nested": {"a": [1, True]},
        },
    )
    second = Event(timestamp=event.timestamp, data={"other": "-formula"})
    rows = list(csv.reader(events_to_csv([event, second])))
    assert rows[0] == [
        "id",
        "timestamp",
        "duration",
        "data.id",
        "data.data.id",
        "title",
        "null",
        "nested",
        "other",
    ]
    assert rows[1] == [
        "7",
        "2025-12-31T23:00:00+00:00",
        "1.234567000",
        "'=1+1",
        "' @command",
        'å,"line\nnext',
        "null",
        '{"a":[1,true]}',
        "",
    ]
    assert rows[2][3:8] == [""] * 5
    assert rows[2][8] == "'-formula"


def test_legacy_nonobject_csv_wide_object_fallback_unchanged():
    data = {f"key{i}": i for i in range(MAX_CSV_DATA_COLUMNS + 1)}
    rows = list(csv.reader(events_to_csv([Event(data=data)])))
    assert rows[0] == ["id", "timestamp", "duration", "data"]
    assert json.loads(rows[1][3]) == data
