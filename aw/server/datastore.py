import logging
from datetime import datetime
from typing import Mapping, List, Union, Sequence

from aw.core.models import Event

logger = logging.getLogger("aw.server.datastore")

try:
    import pymongo
except ImportError:
    logger.warning("Could not import pymongo, not available as a datastore backend")


class Activity(dict):
    pass


MEMORY = "memory"
MONGODB = "mongodb"

# For storage of data in-memory, useful in testing
_memorydb = {}  # type: Mapping[str, Mapping[str, List[Event]]]


class Datastore:
    def __init__(self, storage_method=MEMORY, testing=False):
        if storage_method not in [MEMORY, MONGODB]:
            raise Exception("Invalid storage method")

        self.storage_method = storage_method

        if self.storage_method == MONGODB:
            client = pymongo.MongoClient()
            db = client["activitywatch" if not testing else "activitywatch_testing"]
            self.activities = db.activities

    def insert(self, event_type: str, events: Union[Event, Sequence[Event]]):
        if isinstance(events, Event):
            self._insert_one(event_type, events)
        elif isinstance(events, Sequence):
            self._insert_many(event_type, events)

    def _insert_one(self, event_type: str, event: Event):
        event["type"] = event_type
        event["stored_at"] = datetime.now().isoformat()
        if self.storage_method == MEMORY:
            if event_type not in _memorydb:
                _memorydb[event_type] = []
            _memorydb[event_type].append(event)
        elif self.storage_method == MONGODB:
            self.activities.insert_one(event)

    def _insert_many(self, event_type: str, events: Sequence[Event]):
        for activity in events:
            self._insert_one(event_type, activity)

    def get(self, event_type: str):
        if self.storage_method == MEMORY:
            return _memorydb[event_type] if event_type in _memorydb else []
        elif self.storage_method == MONGODB:
            return list(self.activities.find({"type": event_type}, {"_id": 0}))


