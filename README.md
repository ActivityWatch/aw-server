aw-server
============

[![Build Status](https://github.com/ActivityWatch/aw-server/workflows/Build/badge.svg?branch=master)](https://github.com/ActivityWatch/aw-server/actions?query=workflow%3ABuild+branch%3Amaster)
[![Coverage Status](https://codecov.io/gh/ActivityWatch/aw-server/branch/master/graph/badge.svg)](https://codecov.io/gh/ActivityWatch/aw-server)


ActivityWatch server, for secure storage and retrieval of all your Quantified Self data.

**Note:** In the future this will no longer be the default server used by ActivityWatch, instead we will be using [aw-server-rust](https://github.com/ActivityWatch/aw-server-rust/). The fate of this repo is uncertain, but it will likely be around and maintained for a while (as a reference implementation, for prototyping, etc).


## Build and Install

To install program and dependencies, Poetry is required. You'll want to activate a `venv` before building.

```bash
make build
```

The `aw-server` binary should now be available to you in your PATH (if it is set correctly).

## Usage

Run aw-server:

```bash
aw-server
```

To bind explicitly to IPv6 loopback, run `aw-server --host ::1` and open
`http://[::1]:5600`. The default `localhost` binding depends on your system's
address resolution and may listen only on IPv4.

## Development

If you want to run aw-server in development, you probably want to run a
development instance beside your personal (stable) instance. You can do
this by giving aw-server the `--testing` flag. This will start the server
on another port and use a separate datastore.

```bash
aw-server --testing
```


## API Examples

You can also get a very decent API browser by browsing to `localhost:5600` after starting the server.

There are also some API examples in the [documentation](https://docs.activitywatch.net/en/latest/api.html).


## Draft device-addressed API

This branch is implementation work for ActivityWatch/activitywatch#302. It depends
on draft ActivityWatch/aw-core#183 (pinned in `pyproject.toml`), and includes the
local discovery commits from ActivityWatch/aw-server#183 rebased on master.
**Do not release this as a complete Python/Rust identity contract yet.**

With the SQLite backend, `/api/0/devices/<device_id>/buckets/<id>` and its
`events`, `events/count`, `events/<event_id>`, `events/delete`, `heartbeat`,
`export`, and `export/csv` operations use an explicit device scope. Device bucket
listing is `/api/0/devices/<device_id>/buckets/`; scoped queries use
`POST /api/0/devices/<device_id>/query`; scoped full export is
`GET /api/0/devices/<device_id>/export`. `local` and `/api/0/info.device_id`
normalize to the same stored local sentinel. Peer `hostname="!local"` is rejected.
Unsupported Memory/Peewee scoped operations return 501, never global fallback.

Legacy bucket creation is local-only. Other legacy name-addressed operations
retain unique global-name compatibility; ambiguous names return 409 before a
mutation/export response. Bidirectional hostname aliases preserve stored names
and histories. Exact names win. Legacy POST cannot acknowledge a local alias
when subsequent global writes would select another device. Query cache keys
include scope; heartbeat keys use device and resolved canonical bucket ID.
Metadata changes clear query and heartbeat state.

`GET /api/0/devices` includes the local UUID even when empty, plus stored peers.
Peer hostname is a deterministic representative of bucket metadata, not a
latest-hostname registry. `GET /api/0/devices/buckets` groups metadata explicitly;
`GET /api/0/devices/export` uses the same envelope with events:

```json
{"devices": {"source-uuid": {"buckets": {"window": {"id": "window", "device_id": "source-uuid", "type": "test", "client": "watcher", "hostname": "host", "created": "2024-01-01T00:00:00Z", "events": []}}}}}
```

`POST /api/0/devices/import` accepts that envelope, rejects empty or `local`
source identities, and validates enclosing ownership, bucket keys and event
payloads before writes. Local exported ownership becomes the source UUID, so
history stays peer-owned at another server. Existing same-device buckets merge
events and skip duplicates (timestamp, duration, data), matching Rust; an
alias of stored history merges into that row instead of creating a sibling.
Legacy `/import` still rejects existing exact names. Individual groups use
legacy rollback for buckets this call created; a runtime failure can leave
earlier successful groups.
Metadata `data` is preserved. Grouped export streams SQLite rows from one read
snapshot into a private temporary file before responding; failures cannot send
partial JSON with a success status. The response owns the staged file, not a
live database cursor. Concurrent WAL writes are excluded from that snapshot.
Only metadata and one event at a time are retained in memory; legacy exports
keep their existing implementation. No watcher adoption or sync-v2 import is
enabled by this draft.

Run `make test` for the normal fast server slice plus the device HTTP contract.
The pinned draft core is required; tests use temporary file-backed SQLite and
never a production database. Full shared HTTP parity and backend-specific
migration/same-name acceptance still gate removal of Rust's global name guards.

SQLite HTTP requests on worker threads use their own datastore/connection,
closed at request teardown; they share API write serialization, query cache and
pair-keyed heartbeat state, never a mutable scope. This preserves SQLite's
thread ownership check. Grouped export flushes under the write lock, then
stages from a dedicated read-only snapshot connection so later API writes are
not blocked. Event streaming retains the backend's existing time-range
semantics; unbounded archive/timestamp fidelity remains acceptance work.
