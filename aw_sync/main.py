import logging
from pathlib import Path
from datetime import datetime

from aw_core import Event
from aw_server.api import ServerAPI
from aw_datastore.datastore import Datastore
from aw_datastore.storages import PeeweeStorage


def store_latest_to_syncdir():
    # Get the local db, export it
    local_export = export_dbfile()
    save_export_to_db(local_export)


def save_export_to_db(export):
    p = PeeweeStorage(True, filepath='/home/erb/Cosmosync/master_sync.sqlite')
    now = datetime.now()
    p.create_bucket('test', 'test', 'localhost', 'localhost', now)
    print(p.buckets())


def get_apiobject(filepath: str=None):
    # TODO: Open db as read-only
    db = Datastore(lambda testing: None, testing=True)
    db.storage_strategy = PeeweeStorage(testing=True, filepath=filepath)
    api = ServerAPI(db, testing=True)
    return api


def create_testdb(filepath: str=None, hostname: str="unknown-host"):
    api = get_apiobject(filepath)
    bid = "test-" + hostname
    api.create_bucket(bid, "test-type", "aw_sync", hostname)
    print("Created test db")


def export_dbfile(filepath: str=None):
    """Open a db, return the export of that db"""
    api = get_apiobject(filepath)
    export = api.export_all()
    return export
    # TODO: do export, see aw_server.api.ServerAPI


def create_testdbs(testdir):
    create_testdb(testdir + "/sync-test-1.db", hostname="host1")
    create_testdb(testdir + "/sync-test-2.db", hostname="host2")


def merge_exports(exports):
    master = {}
    for export in exports:
        for bid, bucket in export.items():
            if bid in master:
                raise Exception('bucket collision')
            master[bid] = bucket
    return master


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_folder = "/home/erb/Cosmosync/ActivityWatch"
    create_testdbs(sync_folder)

    exports = []
    for filepath in Path('/home/erb/Cosmosync/ActivityWatch/').iterdir():
        export = export_dbfile(str(filepath))
        exports.append(export)

    print("Successfully exported {} databases".format(len(exports)))

    merged_export = merge_exports(exports)
    print(merged_export)
