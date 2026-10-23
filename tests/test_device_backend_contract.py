"""One real-HTTP identity contract for both server implementations.

Set AW_RUST_CONTRACT_BINARY to an absolute aw-server binary to include Rust.
Covers both distinct stored names sharing compatibility aliases and equal names
owned by three devices. Backend-specific raw migration preservation stays separate.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

import pytest


class Server:
    def __init__(self, base):
        self.base = base
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method, path, body=None):
        payload = None if body is None else json.dumps(body).encode()
        request = Request(
            self.base + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw
            return response.status, value


@pytest.fixture(params=["python", "rust"])
def backend(request):
    if request.param == "rust" and not os.environ.get("AW_RUST_CONTRACT_BINARY"):
        pytest.skip("set AW_RUST_CONTRACT_BINARY for the shared Rust HTTP contract")
    return request.param


@pytest.fixture()
def start_server(tmp_path):
    processes = []
    logs = []
    running = {}

    def start(backend, label, restart=False):
        root = tmp_path / label
        if restart:
            process = running.pop(label)
            process.terminate()
            process.wait(timeout=10)
        else:
            root.mkdir()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            env[key] = str(root / key.lower())
            Path(env[key]).mkdir(exist_ok=restart)
        for key in ("AW_PROFILE", "AW_DB_PASSWORD", "AW_SERVER_API_KEY"):
            env.pop(key, None)
        database = str(root / "events.db")
        if backend == "rust":
            binary = Path(os.environ["AW_RUST_CONTRACT_BINARY"])
            assert binary.is_absolute() and binary.is_file()
            command = [
                str(binary),
                "--profile",
                "identity-contract",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--dbpath",
                database,
                "--config",
                str(root / "config.toml"),
                "--no-legacy-import",
                "--device-id",
                label,
            ]
        else:
            command = [
                sys.executable,
                "-c",
                # HTTPServer.server_bind reverse-resolves the bind address with
                # socket.getfqdn before listening; that lookup stalls past the
                # readiness deadline on macOS CI runners. Identity contracts do
                # not depend on the WSGI SERVER_NAME, so skip the DNS round-trip.
                "import socket; socket.getfqdn = lambda name='': name; "
                "from functools import partial; "
                "from aw_datastore.storages import SqliteStorage; "
                "from aw_server.server import AWFlask; "
                "import aw_server.api; "
                f"aw_server.api.get_device_id = lambda: {label!r}; "
                "app = AWFlask('127.0.0.1', testing=True, "
                f"storage_method=partial(SqliteStorage, filepath={database!r}), "
                "cors_origins=[]); "
                f"app.run(host='127.0.0.1', port={port}, threaded=True)",
            ]
        log_path = root / "server.log"
        log = log_path.open("w")
        logs.append(log)
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        processes.append(process)
        running[label] = process
        server = Server(f"http://127.0.0.1:{port}/api/0")
        deadline = time.monotonic() + 20
        last = None
        while time.monotonic() < deadline:
            assert process.poll() is None, log_path.read_text()
            try:
                last = server.request("GET", "/info")
                if last[0] == 200:
                    return server
            except OSError as error:
                last = error
            time.sleep(0.05)
        pytest.fail(
            f"server readiness timeout (last /info: {last!r}): {log_path.read_text()}"
        )

    yield start
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for log in logs:
        log.close()


def metadata(hostname):
    return {"type": "test", "client": "identity-contract", "hostname": hostname}


def event(owner, second=0):
    return {
        "timestamp": f"2026-01-01T00:00:{second:02d}.123456Z",
        "duration": 1.234567,
        "data": {"owner": owner},
    }


def test_shared_scoped_alias_crud_query_and_export(backend, start_server):
    server = start_server(backend, "source-uuid")
    for device, bid, hostname in (
        ("local", "window_old_host", "old_host"),
        ("peer", "window_peer_host", "peer_host"),
    ):
        base = f"/devices/{device}/buckets/window"
        status, body = server.request(
            "POST", f"/devices/{device}/buckets/{bid}", metadata(hostname)
        )
        assert status == 200, body
        assert server.request("POST", base, metadata(hostname))[0] == 304
        status, rows = server.request("POST", base + "/events", [event(device)])
        assert status == 200, rows
        eid = rows[0]["id"]
        assert server.request("GET", base + "/events/count") == (200, 1)
        status, row = server.request("GET", base + f"/events/{eid}")
        assert status == 200 and row["data"] == {"owner": device}
        assert row["duration"] == 1.234567
        assert ".123456" in row["timestamp"]
        query = {
            "query": ['RETURN = query_bucket("window");'],
            "timeperiods": ["2026-01-01T00:00:00Z/2026-01-02T00:00:00Z"],
        }
        status, result = server.request("POST", f"/devices/{device}/query", query)
        assert status == 200, result
        assert result[0][0]["data"] == {"owner": device}
        for suffix in ("export", "export/csv"):
            status, archive = server.request("GET", base + "/" + suffix)
            assert status == 200, archive
            assert device in str(archive)
        # UUID and sentinel address exactly the same local history.
        if device == "local":
            assert server.request(
                "GET", "/devices/source-uuid/buckets/window/events"
            ) == server.request("GET", base + "/events")
    assert server.request("GET", "/buckets/window")[0] == 409
    status, grouped = server.request("GET", "/devices/export")
    assert status == 200, grouped
    assert set(grouped["devices"]) == {"source-uuid", "peer"}
    for device in ("local", "peer"):
        base = f"/devices/{device}/buckets/window"
        status, rows = server.request("GET", base + "/events")
        assert status == 200
        status, body = server.request("DELETE", base + f"/events/{rows[0]['id']}")
        assert status == 200, body
        assert server.request("GET", base + "/events/count") == (200, 0)
        status, body = server.request("DELETE", base)
        assert status == 200, body
        assert server.request("GET", base)[0] == 404


def test_shared_same_name_three_devices_query_export_and_reader_refresh(
    backend, start_server
):
    server = start_server(backend, "source-uuid")
    query = {
        "query": ['RETURN = query_bucket("window");'],
        "timeperiods": ["2026-01-01T00:00:00Z/2026-01-02T00:00:00Z"],
    }
    devices = ("local", "peer", "third")
    for device in devices:
        base = f"/devices/{device}/buckets/window"
        status, body = server.request("POST", base, metadata(f"{device}_host"))
        assert status == 200, body
        assert server.request("POST", base, metadata(f"{device}_host"))[0] == 304
        status, rows = server.request("POST", base + "/events", [event(device)])
        assert status == 200, rows
        # Querying after each write opens/reuses the actual backend reader/cache.
        status, result = server.request("POST", f"/devices/{device}/query", query)
        assert status == 200 and result[0][0]["data"] == {"owner": device}, result
    for device in devices:
        base = f"/devices/{device}/buckets/window"
        assert server.request("GET", base + "/events/count") == (200, 1)
        status, rows = server.request("GET", base + "/events")
        assert status == 200 and len(rows) == 1 and rows[0]["data"] == {"owner": device}
        status, result = server.request("POST", f"/devices/{device}/query", query)
        assert status == 200 and result[0][0]["data"] == {"owner": device}, result
        status, archive = server.request("GET", base + "/export")
        assert status == 200, archive
        assert archive["buckets"]["window"]["events"][0]["data"] == {"owner": device}
        status, csv = server.request("GET", base + "/export/csv")
        assert status == 200 and device in csv, csv
        # Globally unique hostname aliases still address the resolved device.
        assert server.request(
            "GET", f"/buckets/window_{device}_host/events"
        ) == server.request("GET", base + "/events")
    # Alias writes must keep their resolved owner across nested API operations,
    # not just reads. Identical heartbeat data must never cross device state.
    for device in devices:
        alias = f"/buckets/window_{device}_host"
        status, rows = server.request("POST", alias + "/events", [event(device, 10)])
        assert status == 200 and len(rows) == 1, rows
        event_id = rows[0]["id"]
        status, body = server.request("DELETE", alias + f"/events/{event_id}")
        assert status == 200, body
        assert server.request("GET", alias + "/events/count") == (200, 1)
        for second in (2, 5):
            heartbeat = event(device, second)
            heartbeat["duration"] = 0
            status, body = server.request(
                "POST", alias + "/heartbeat?pulsetime=10", heartbeat
            )
            assert status == 200, body
        status, rows = server.request("GET", alias + "/events")
        assert status == 200 and len(rows) == 1, rows
        assert rows[0]["data"] == {"owner": device}
        assert rows[0]["duration"] == 5
    # Python's catalogue has a canonical trailing slash. Python 3.9 urllib
    # does not follow Flask's 308 redirect, unlike newer local interpreters.
    catalogue = "/buckets/" if backend == "python" else "/buckets"
    for path in ("/buckets/window", catalogue, "/export"):
        assert server.request("GET", path)[0] == 409, path
    assert server.request(
        "GET", "/devices/source-uuid/buckets/window/events"
    ) == server.request("GET", "/devices/local/buckets/window/events")
    status, grouped = server.request("GET", "/devices/export")
    assert status == 200, grouped
    assert set(grouped["devices"]) == {"source-uuid", "peer", "third"}
    for owner, exported in (
        ("local", "source-uuid"),
        ("peer", "peer"),
        ("third", "third"),
    ):
        assert grouped["devices"][exported]["buckets"]["window"]["events"][0][
            "data"
        ] == {"owner": owner}
    for device in ("third", "peer"):
        status, body = server.request("DELETE", f"/devices/{device}/buckets/window")
        assert status == 200, body
        assert server.request("GET", f"/devices/{device}/buckets/window")[0] == 404
        status, result = server.request("POST", "/devices/local/query", query)
        assert status == 200 and result[0][0]["data"] == {"owner": "local"}, result
    assert server.request("GET", "/buckets/window")[1]["device_id"] == "local"


def test_shared_grouped_transfer_preserves_ownership_and_is_idempotent(
    backend, start_server
):
    source = start_server(backend, "source-uuid")
    target = start_server(backend, "target-uuid")
    base = "/devices/local/buckets/archive"
    assert source.request("POST", base, metadata("old_host"))[0] == 200
    assert source.request("POST", base + "/events", [event("source")])[0] == 200
    status, archive = source.request("GET", "/devices/export")
    assert status == 200
    for _ in range(2):
        status, body = target.request("POST", "/devices/import", archive)
        assert status == 200, body
    imported = "/devices/source-uuid/buckets/archive"
    assert target.request("GET", imported + "/events/count") == (200, 1)
    assert target.request("GET", "/devices/local/buckets/archive")[0] == 404
    status, rows = target.request("GET", imported + "/events")
    assert status == 200
    assert rows[0]["data"] == {"owner": "source"}
    assert rows[0]["duration"] == 1.234567
    assert ".123456" in rows[0]["timestamp"]


@pytest.mark.parametrize(
    "source_backend,target_backend", [("python", "rust"), ("rust", "python")]
)
def test_cross_backend_grouped_transfer(source_backend, target_backend, start_server):
    if not os.environ.get("AW_RUST_CONTRACT_BINARY"):
        pytest.skip("cross-backend transfer requires AW_RUST_CONTRACT_BINARY")
    source = start_server(source_backend, "source-uuid")
    target = start_server(target_backend, "target-uuid")
    base = "/devices/local/buckets/archive_old_host"
    assert source.request("POST", base, metadata("old_host"))[0] == 200
    assert source.request("POST", base + "/events", [event("source")])[0] == 200
    status, archive = source.request("GET", "/devices/export")
    assert status == 200
    for _ in range(2):
        status, body = target.request("POST", "/devices/import", archive)
        assert status == 200, body
    imported = "/devices/source-uuid/buckets/archive"
    assert target.request("GET", imported + "/events/count") == (200, 1)
    status, rows = target.request("GET", imported + "/events")
    assert status == 200
    assert rows[0]["data"] == {"owner": "source"}
    assert rows[0]["duration"] == 1.234567
    assert ".123456" in rows[0]["timestamp"]
    assert target.request("GET", "/devices/local/buckets/archive")[0] == 404


@pytest.mark.parametrize(
    "source_backend,target_backend", [("python", "rust"), ("rust", "python")]
)
def test_cross_backend_same_names_roundtrip_without_cross_device_merge(
    source_backend, target_backend, start_server
):
    if not os.environ.get("AW_RUST_CONTRACT_BINARY"):
        pytest.skip("cross-backend transfer requires AW_RUST_CONTRACT_BINARY")
    source = start_server(source_backend, "source-uuid")
    target = start_server(target_backend, "target-uuid")
    base = "/devices/local/buckets/window"
    assert target.request("POST", base, metadata("target_host"))[0] == 200
    assert target.request("POST", base + "/events", [event("target")])[0] == 200
    for device in ("local", "peer", "third"):
        scoped = f"/devices/{device}/buckets/window"
        assert source.request("POST", scoped, metadata(f"{device}_host"))[0] == 200
        assert source.request("POST", scoped + "/events", [event(device)])[0] == 200
    status, archive = source.request("GET", "/devices/export")
    assert status == 200, archive
    for _ in range(2):
        status, body = target.request("POST", "/devices/import", archive)
        assert status == 200, body
    for source_device, target_device in (
        ("local", "source-uuid"),
        ("peer", "peer"),
        ("third", "third"),
    ):
        scoped = f"/devices/{target_device}/buckets/window"
        status, rows = target.request("GET", scoped + "/events")
        assert status == 200 and len(rows) == 1, rows
        assert rows[0]["data"] == {"owner": source_device}
        assert target.request("GET", scoped)[1]["device_id"] == target_device
    status, rows = target.request("GET", base + "/events")
    assert (
        status == 200 and len(rows) == 1 and rows[0]["data"] == {"owner": "target"}
    ), rows
    assert target.request("GET", "/buckets/window")[0] == 409
    # Re-exporting back does not duplicate the source's local UUID into a peer.
    status, returned = target.request("GET", "/devices/export")
    assert status == 200, returned
    for _ in range(2):
        status, body = source.request("POST", "/devices/import", returned)
        assert status == 200, body
    status, rows = source.request("GET", base + "/events")
    assert (
        status == 200 and len(rows) == 1 and rows[0]["data"] == {"owner": "local"}
    ), rows
    status, rows = source.request("GET", "/devices/target-uuid/buckets/window/events")
    assert (
        status == 200 and len(rows) == 1 and rows[0]["data"] == {"owner": "target"}
    ), rows


def test_shared_heartbeat_alias_state_and_local_ownership(backend, start_server):
    server = start_server(backend, "source-uuid")
    for device, host in (("local", "old_host"), ("peer", "peer_host")):
        base = f"/devices/{device}/buckets/window_{host}"
        assert server.request("POST", base, metadata(host))[0] == 200
        for second, name in ((0, f"window_{host}"), (5, "window")):
            heartbeat = event(device, second)
            heartbeat["duration"] = 0
            status, body = server.request(
                "POST",
                f"/devices/{device}/buckets/{name}/heartbeat?pulsetime=10",
                heartbeat,
            )
            assert status == 200, body
        status, rows = server.request("GET", base + "/events")
        assert status == 200 and len(rows) == 1, rows
        assert rows[0]["duration"] == 5
        assert rows[0]["data"] == {"owner": device}
        assert (
            server.request("GET", f"/devices/{device}/buckets/window_unknown_host")[0]
            == 404
        )
    forged = metadata("!local")
    forged["device_id"] = "peer"
    forged["data"] = {"device_id": "peer"}
    status, body = server.request("POST", "/buckets/new_local", forged)
    assert status == 200, body
    assert (
        server.request("GET", "/devices/local/buckets/new_local")[1]["device_id"]
        == "local"
    )
    assert server.request("GET", "/devices/peer/buckets/new_local")[0] == 404


def test_shared_same_name_identical_heartbeats_keep_device_state(backend, start_server):
    server = start_server(backend, "source-uuid")
    for device in ("local", "peer"):
        assert (
            server.request(
                "POST", f"/devices/{device}/buckets/window", metadata(f"{device}_host")
            )[0]
            == 200
        )
    ids = {}
    # The payloads are identical; differing data must not accidentally hide
    # a cache that is keyed only by the shared stored name.
    for device, second in (("local", 0), ("peer", 2), ("local", 5), ("peer", 9)):
        heartbeat = event("same", second)
        heartbeat["duration"] = 0
        status, row = server.request(
            "POST", f"/buckets/window_{device}_host/heartbeat?pulsetime=10", heartbeat
        )
        assert status == 200, row
        if device in ids:
            assert row["id"] == ids[device]
        ids[device] = row["id"]
    assert ids["local"] != ids["peer"]
    for device, duration, second in (("local", 5, "00"), ("peer", 7, "02")):
        status, rows = server.request("GET", f"/devices/{device}/buckets/window/events")
        assert status == 200 and len(rows) == 1, rows
        assert rows[0]["duration"] == duration
        assert f"00:00:{second}.123456" in rows[0]["timestamp"]
        assert rows[0]["data"] == {"owner": "same"}


def test_shared_separator_alias_ambiguity(backend, start_server):
    server = start_server(backend, "source-uuid")
    for bid, hostname in (
        ("a", "b_c"),
        ("a_b", "c"),
        ("window", "old"),
        ("window_new", "other"),
    ):
        base = f"/devices/local/buckets/{bid}"
        status, body = server.request("POST", base, metadata(hostname))
        assert status == 200, body
        assert server.request("POST", base + "/events", [event(bid)])[0] == 200
    status, before = server.request("GET", "/devices/export")
    assert status == 200, before
    # a + '_' + b_c and a_b + '_' + c are both plausible. Never split
    # the requested name and select one arbitrarily.
    for method, suffix, payload in (
        ("GET", "/events", None),
        ("POST", "/events", [event("must-not-land")]),
        ("DELETE", "", None),
    ):
        assert (
            server.request(method, "/devices/local/buckets/a_b_c" + suffix, payload)[0]
            == 409
        )
    assert server.request("GET", "/devices/export") == (200, before)


def test_python_metadata_repair_preserves_exact_match_priority(start_server):
    # Rust has no metadata PUT route; its exact-first resolver is tested in
    # aw-datastore. Do not invent a new HTTP surface to seed this legacy state.
    server = start_server("python", "source-uuid")
    for bid, hostname in (("window", "old"), ("window_new", "other")):
        base = f"/devices/local/buckets/{bid}"
        assert server.request("POST", base, metadata(hostname))[0] == 200
        assert server.request("POST", base + "/events", [event(bid)])[0] == 200
    # Metadata repair can make an alias collide with an existing exact name.
    # Resolution must still prefer that exact row, without merging history.
    status, body = server.request(
        "PUT", "/devices/local/buckets/window", {"hostname": "new"}
    )
    assert status == 200, body
    for bid in ("window", "window_new"):
        status, rows = server.request("GET", f"/devices/local/buckets/{bid}/events")
        assert status == 200 and rows[0]["data"] == {"owner": bid}, rows


def test_shared_same_names_survive_process_restart(backend, start_server):
    server = start_server(backend, "source-uuid")
    devices = ("local", "peer", "third")
    for device in devices:
        base = f"/devices/{device}/buckets/window"
        assert server.request("POST", base, metadata(f"{device}_host"))[0] == 200
        assert server.request("POST", base + "/events", [event(device)])[0] == 200
    status, before = server.request("GET", "/devices/export")
    assert status == 200, before
    server = start_server(backend, "source-uuid", restart=True)
    assert server.request("GET", "/devices/export") == (200, before)
    for device in devices:
        base = f"/devices/{device}/buckets/window"
        status, rows = server.request("GET", base + "/events")
        assert status == 200 and rows[0]["data"] == {"owner": device}, rows
        assert server.request("GET", f"/buckets/window_{device}_host/events") == (
            200,
            rows,
        )
        assert server.request("POST", base, metadata(f"{device}_host"))[0] == 304
    assert server.request("GET", "/buckets/window")[0] == 409
    assert server.request("DELETE", "/devices/peer/buckets/window")[0] == 200
    server = start_server(backend, "source-uuid", restart=True)
    assert server.request("GET", "/devices/peer/buckets/window")[0] == 404
    for device in ("local", "third"):
        status, rows = server.request("GET", f"/devices/{device}/buckets/window/events")
        assert status == 200 and rows[0]["data"] == {"owner": device}, rows


def test_shared_ambiguous_aliases_fail_before_reads_and_writes(backend, start_server):
    server = start_server(backend, "source-uuid")
    for device in ("local", "peer"):
        for suffix in ("alpha_host", "beta_host"):
            base = f"/devices/{device}/buckets/window_{suffix}"
            status, body = server.request("POST", base, metadata(suffix))
            assert status == 200, body
            assert (
                server.request("POST", base + "/events", [event(f"{device}:{suffix}")])[
                    0
                ]
                == 200
            )
    status, before = server.request("GET", "/devices/export")
    assert status == 200, before
    query = {
        "query": ['RETURN = query_bucket("window");'],
        "timeperiods": ["2026-01-01T00:00:00Z/2026-01-02T00:00:00Z"],
    }
    for device in ("local", "peer"):
        base = f"/devices/{device}/buckets/window"
        for method, suffix, payload in (
            ("GET", "", None),
            ("GET", "/events", None),
            ("GET", "/events/count", None),
            ("GET", "/export", None),
            ("POST", "", metadata("alpha_host")),
            ("POST", "/events", [event("must-not-land")]),
            ("POST", "/heartbeat?pulsetime=10", event("must-not-land")),
            ("DELETE", "", None),
        ):
            status, body = server.request(method, base + suffix, payload)
            assert status == 409, (device, method, suffix, body)
        assert server.request("POST", f"/devices/{device}/query", query)[0] == 409
        # Exact spellings remain addressable despite ambiguous aliases and
        # equal names on another device, including underscore-bearing hosts.
        for suffix in ("alpha_host", "beta_host"):
            base = f"/devices/{device}/buckets/window_{suffix}"
            status, rows = server.request("GET", base + "/events")
            assert status == 200 and rows[0]["data"] == {
                "owner": f"{device}:{suffix}"
            }, rows
            assert server.request("GET", base + "_unknown_host")[0] == 404
    assert server.request("GET", "/devices/export") == (200, before)


def test_shared_separator_components_keep_distinct_pair_identity(backend, start_server):
    server = start_server(backend, "source-uuid")
    # These pairs collide if an implementation joins components with ':'.
    # Percent escapes must decode once, independently of the other component.
    pairs = (
        ("peer:part", "window"),
        ("peer", "part:window"),
        ("peer%3Apart", "window%3Aname"),
    )
    for index, (device, bid) in enumerate(pairs):
        base = f"/devices/{quote(device, safe='')}/buckets/{quote(bid, safe='')}"
        status, body = server.request("POST", base, metadata("host_with_underscores"))
        assert status == 200, body
        assert server.request("POST", base + "/events", [event(str(index))])[0] == 200
    for index, (device, bid) in enumerate(pairs):
        base = f"/devices/{quote(device, safe='')}/buckets/{quote(bid, safe='')}"
        status, body = server.request("GET", base)
        assert status == 200 and body["id"] == bid and body["device_id"] == device, body
        assert server.request("GET", base + "/events")[1][0]["data"] == {
            "owner": str(index)
        }
        query = {
            "query": [f"RETURN = query_bucket({json.dumps(bid)});"],
            "timeperiods": ["2026-01-01T00:00:00Z/2026-01-02T00:00:00Z"],
        }
        status, rows = server.request(
            "POST", f"/devices/{quote(device, safe='')}/query", query
        )
        assert status == 200 and rows[0][0]["data"] == {"owner": str(index)}, rows
    status, grouped = server.request("GET", "/devices/export")
    assert status == 200, grouped
    for index, (device, bid) in enumerate(pairs):
        bucket = grouped["devices"][device]["buckets"][bid]
        assert bucket["id"] == bid and bucket["device_id"] == device
        assert bucket["events"][0]["data"] == {"owner": str(index)}


def test_shared_legacy_import_rejects_same_name_ambiguity_without_mutation(
    backend, start_server
):
    server = start_server(backend, "source-uuid")
    for device in ("local", "peer", "third"):
        base = f"/devices/{device}/buckets/window"
        assert server.request("POST", base, metadata(f"{device}_host"))[0] == 200
        assert server.request("POST", base + "/events", [event(device)])[0] == 200
    status, before = server.request("GET", "/devices/export")
    assert status == 200, before
    incoming = dict(before["devices"]["source-uuid"]["buckets"]["window"])
    incoming["events"] = [event("must-not-land", 20)]
    # Legacy Python import rejects existing IDs (400); Rust's name-addressed
    # compatibility importer rejects ambiguity (409). Neither may pick local,
    # redirect to a peer or merge into an arbitrary equal-name history.
    status, body = server.request("POST", "/import", {"buckets": {"window": incoming}})
    assert status == (400 if backend == "python" else 409), body
    assert server.request("GET", "/devices/export") == (200, before)
