import json
import os
import logging
from typing import Mapping, List, Union, Sequence

import appdirs

from aw.core.models import Event

try:
    import pymongo
except ImportError:
    logger.warning("Could not import pymongo, not available as a datastore backend")


class StorageStrategy():
    """
    Interface for storage methods.

    Implementations require:
     - insert_one
     - get

    Optional:
     - insert_many
    """

    def get(self, bucket: str):
        raise NotImplementedError

    def insert(self, bucket: str, events: Union[Event, Sequence[Event]]):
        if isinstance(events, dict) or isinstance(events, Sequence[dict]):
            logging.warning("Events are of type dict, please turn them into proper Events")

        if isinstance(events, Event) or isinstance(events, dict):
            self.insert_one(bucket, events)
        elif isinstance(events, Sequence):
            self.insert_many(bucket, events)
        else:
            print("Argument events wasn't a valid type")

    def insert_one(self, bucket: str, event: Event):
        raise NotImplementedError

    def insert_many(self, bucket: str, events: Sequence[Event]):
        for activity in events:
            self.insert_one(bucket, activity)


class MongoDBStorageStrategy(StorageStrategy):
    """Uses a MongoDB server as backend"""

    def __init__(self):
        self.logger = logging.getLogger("datastore-mongodb")

        if 'pymongo' not in vars() and 'pymongo' not in globals():
            logger.error("Cannot use the MongoDB backend without pymongo installed")
            exit(1)

        try:
            self.client = pymongo.MongoClient(serverSelectionTimeoutMS=5000)
            self.client.server_info() # Try to connect to the server to make sure that it's available
        except pymongo.errors.ServerSelectionTimeoutError:
        	logger.error("Couldn't connect to MongoDB server at localhost")
        	exit(1)

        # TODO: Readd testing ability
        #self.db = self.client["activitywatch" if not testing else "activitywatch_testing"]
        self.db = self.client["activitywatch"]

    def get(self, bucket: str):
        return list(self.db[bucket].find())

    def insert_one(self, bucket: str, event: Event):
        self.db[bucket].insert_one(event)


class MemoryStorageStrategy(StorageStrategy):
    """For storage of data in-memory, useful primarily in testing"""

    def __init__(self):
        self.logger = logging.getLogger("datastore-memory")
        self.logger.warning("Using in-memory storage, any events stored will not be persistent and will be lost when server is shut down. Use the --storage parameter to set a different storage method.")
        self.db = {}  # type: Mapping[str, Mapping[str, List[Event]]]

    def get(self, bucket: str):
        if bucket not in self.db:
            return []
        return self.db[bucket]

    def insert_one(self, bucket: str, event: Event):
        if bucket not in self.db:
            self.db[bucket] = []
        self.db[bucket].append(event)


class FileStorageStrategy(StorageStrategy):
    """For storage of data in JSON files, useful as a zero-dependency/databaseless solution"""

    def __init__(self):
        self.logger = logging.getLogger("datastore-files")

    def get_filename(self, bucket: str):
        directory = appdirs.user_data_dir("aw-server", "activitywatch")
        if not os.path.exists(directory):
            os.makedirs(directory)
        return "{directory}/{bucket}.json".format(directory=directory, bucket=bucket)

    def get(self, bucket: str):
        filename = self.get_filename(bucket)
        if not os.path.isfile(filename):
            return []
        with open(filename) as f:
            data = json.load(f)
        return data

    def insert_one(self, bucket: str, event: Event):
        self.insert_many(bucket, [event])

    def insert_many(self, bucket: str, events: Sequence[Event]):
        filename = self.get_filename(bucket)

        if os.path.isfile(filename):
            with open(filename, "r") as f:
                data = json.load(f)
        else:
            data = []

        data.extend(events)
        with open(filename, "w") as f:
            json.dump(data, f)
