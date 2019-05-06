import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Union
import os

from aw_core import Event
from aw_client import ActivityWatchClient
from aw_server.api import ServerAPI
from aw_datastore.datastore import Datastore
from aw_datastore.storages import SqliteStorage

SYNC_FOLDER = "/home/erb/Cosmosync/ActivityWatch"

AWAPI = Union[ActivityWatchClient, ServerAPI]


def save_export_to_db(export):
    p = SqliteStorage(testing=True, filepath=SYNC_FOLDER + '/master_sync.sqlite')
    now = datetime.now(tz=timezone.utc)
    p.create_bucket('test', 'test', 'localhost', 'localhost', now)
    print(p.buckets())


def get_apiobject(filepath: Path) -> ServerAPI:
    # TODO: Open db as read-only
    os.makedirs(filepath.parent, exist_ok=True)
    db = Datastore((lambda testing: None), testing=True)
    db.storage_strategy = SqliteStorage(testing=True, filepath=filepath, enable_lazy_commit=False)
    api = ServerAPI(db, testing=True)
    return api


def create_testdbs(testpath: Path):
    create_testdb(testpath / "sync-test-1.sqlite", hostname="host1")
    create_testdb(testpath / "sync-test-2.sqlite", hostname="host2")


def create_testdb(filepath: Path, hostname: str="unknown-host"):
    api = get_apiobject(filepath)
    bid = "test-" + hostname
    if bid not in api.get_buckets():
        api.create_bucket(bid, "test-type", "aw_sync", hostname)
        api.create_events(bid, [Event(data={"test": 1})])
        print(f"Created test db {bid}")


# Sync new events
def sync_bucket(api_from: AWAPI, api_to: AWAPI, bucket_id_from: str, bucket_id_to: str) -> None:
    api_from = universalize_api_accessor(api_from)
    api_to = universalize_api_accessor(api_to)

    print(f"Syncing {bucket_id_from} to {api_to}...")

    buckets_to = api_to.get_buckets()
    if bucket_id_to not in buckets_to:
        # Do full first import
        export = api_from.export_bucket(bucket_id_from)
        export['id'] = bucket_id_to
        api_to.import_bucket(export)
        print(f"Imported new bucket {bucket_id_from} as {bucket_id_to}!")
    else:
        last_event_local = api_to.get_events(bucket_id_from, limit=1) or None
        if last_event_local:
            last_event_local = last_event_local[0]
            synced_until = last_event_local.timestamp
        else:
            synced_until = None
        new_events = sorted(api_from.get_events(bucket_id_from, start=synced_until, limit=-1), key=lambda e: e.timestamp)

        # Send the first event as a heartbeat, as it could be an updated version of the last local event
        if len(new_events) > 0:
            first_new_event = new_events[0]
            if last_event_local.timestamp == first_new_event.timestamp:
                api_to.heartbeat(bucket_id_to, first_new_event, 0)

        #for e in new_events:
        #    print(e)

        new_events = new_events[1:]
        # Unset the ID for the new events
        for e in new_events:
            e['id'] = None

        api_to.insert_events(bucket_id_to, new_events)  # type: ignore

        print(f"Fetched {len(new_events)} new events from {bucket_id_from}!")


# Used to universalize API of ActivityWatchClient and ServerAPI by monkeypatching
def universalize_api_accessor(api: AWAPI) -> AWAPI:
    if isinstance(api, ActivityWatchClient):
        api.create_events = api.insert_events
    elif isinstance(api, ServerAPI):
        api.insert_events = api.create_events  # type: ignore

    if isinstance(api, ActivityWatchClient):
        import types

        orig_export_bucket = api.export_bucket

        def export_bucket_new(self, bucket_id):
            export = orig_export_bucket(bucket_id)
            return export["buckets"][bucket_id]

        if api.export_bucket.__name__ != export_bucket_new.__name__:
            print("monkeypatched export_bucket")
            api.export_bucket = types.MethodType(export_bucket_new, api)

    return api


def incremental_export() -> None:
    """Open a db, return the export of that db"""
    test_folder = Path(SYNC_FOLDER + "/test-incremental")
    create_testdbs(test_folder)

    # API of local sync database
    # TODO: Give sync files unique, identifiable, names
    filepath_local = test_folder / 'main.sqlite'
    api_local = get_apiobject(filepath_local)

    # Push all changes to the sync db of localhost
    awc = ActivityWatchClient(testing=True)
    for bucket_id in awc.get_buckets():
        sync_bucket(awc, api_local, bucket_id, bucket_id)

    # Fetch all changes to the local db of localhost
    for filepath in Path(test_folder).glob('*.sqlite'):
        if filepath == filepath_local:
            continue
        api_from = get_apiobject(Path(filepath))
        buckets_remote = api_from.get_buckets()

        # TODO: Be careful which buckets get synced! There might be bucket-name collisions!
        for bucket_id in buckets_remote:
            sync_bucket(api_from, awc, bucket_id, bucket_id + "-remote-test")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    incremental_export()
