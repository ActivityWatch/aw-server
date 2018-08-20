from pathlib import Path
from datetime import datetime

from aw_core import Event
from aw_datastore.storages import PeeweeStorage


def store_latest_to_syncdir():
    # Get the local db, export it
    local_export = export_dbfile()
    save_export_to_db(local_export)


def save_export_to_db(export):
    p = PeeweeStorage(True, filepath='/home/erb/Cosmosync/test.sqlite')
    now = datetime.now()
    p.create_bucket('test', 'test', 'localhost', 'localhost', now)
    print(p.buckets())
    # TODO: do export, see aw_server.api.ServerAPI


def export_dbfile(filepath):
    """Open a db, return the export of that db"""
    # TODO: Open db as read-only
    p = PeeweeStorage(True)
    now = datetime.now()
    p.create_bucket('test', 'test', 'localhost', 'localhost', now)
    print(p.buckets())
    # TODO: do export, see aw_server.api.ServerAPI


for filepath in Path('/home/erb/Cosmosync/ActivityWatch/').iterdir():
    print(filepath)
