import logging
from datetime import datetime
from typing import Mapping, List, Union, Sequence
import json

from aw.core.models import Event

from .storage_strategies import *

logger = logging.getLogger("aw.server.datastore")


MEMORY = MemoryStorageStrategy
FILES = FileStorageStrategy
MONGODB = MongoDBStorageStrategy

class Datastore:
    def __init__(self, storage_strategy: StorageStrategy = MEMORY, testing=False):
        self.logger = logging.getLogger("datastore")

        if storage_strategy not in [MEMORY, MONGODB, FILES]:
            raise Exception("Unsupported storage medium: {}".format(storage_method))

        self.storage_strategy = storage_strategy()

    def __getitem__(self, bucket_id: str):
        return Bucket(self, bucket_id)

class Bucket:
    def __init__(self, datastore: Datastore, bucket_id: str):
        self.ds = datastore
        self.bucket_id = bucket_id

    def get(self):
        return self.ds.storage_strategy.get(self.bucket_id)

    def insert(self, events: Union[Event, Sequence[Event]]):
        return self.ds.storage_strategy.insert(self.bucket_id, events)

    def insert_one(self, event: Event):
        return self.ds.storage_strategy.insert_one(self.bucket_id, event)

    def insert_many(self, events: Sequence[Event]):
        return self.ds.storage_strategy.insert_many(self.bucket_id, events)
