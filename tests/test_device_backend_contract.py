"""One real-HTTP identity contract for both server implementations.

Set AW_RUST_CONTRACT_BINARY to an absolute aw-server binary to include Rust.
The Rust draft still rejects exact same-name coexistence; these shared cases
exercise distinct stored names with the same device-scoped compatibility alias.
Backend-specific same-name/migration tests remain required before guard removal.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
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

    def start(backend, label):
        root = tmp_path / label
        root.mkdir()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            env[key] = str(root / key.lower())
            Path(env[key]).mkdir()
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
        server = Server(f"http://127.0.0.1:{port}/api/0")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, log_path.read_text()
            try:
                if server.request("GET", "/info")[0] == 200:
                    return server
            except OSError:
                pass
            time.sleep(0.05)
        pytest.fail(f"server readiness timeout: {log_path.read_text()}")

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
