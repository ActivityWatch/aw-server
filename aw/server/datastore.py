import json
from datetime import datetime
from typing import Mapping, List, Union
import logging

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
_activitydb = {}  # type: Mapping[str, List[Activity]]

class ActivityDatastore:
    def __init__(self, storage_method=MEMORY, testing=False):
        if storage_method in [MEMORY, MONGODB]:
            pass
        else:
            raise Exception("Invalid storage method")

        self.storage_method = storage_method

        if self.storage_method == MONGODB:
            self.client = pymongo.MongoClient()
            self.db = self.client["activitywatch" if not testing else "activitywatch_testing"]
            self.activities = self.db.activities

    def insert(self, activity_type: str, one_or_more_activities: Union[list, dict]):
        if isinstance(one_or_more_activities, list):
            self._insert_many(activity_type, one_or_more_activities)
        elif isinstance(one_or_more_activities, dict):
            self._insert_one(activity_type, one_or_more_activities)

    def _insert_one(self, activity_type: str, activity: dict):
        activity["type"] = activity_type
        activity["stored_at"] = datetime.now().isoformat()
        if self.storage_method == MEMORY:
            if activity_type not in _activitydb:
                _activitydb[activity_type] = []
            _activitydb[activity_type].append(activity)
        elif self.storage_method == MONGODB:
            self.activities.insert_one(activity)

    def _insert_many(self, activity_type: str, activities: dict):
        for activity in activities:
            self._insert_one(activity_type, activity)

    def get(self, activity_type: str):
        if self.storage_method == MEMORY:
            return _activitydb[activity_type] if activity_type in _activitydb else []
        elif self.storage_method == MONGODB:
            return list(self.activities.find({"type": activity_type}, {"_id": 0}))


