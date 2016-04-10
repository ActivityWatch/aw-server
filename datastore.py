import json
from typing import Mapping, List

try:
    import pymongo
except ImportError:
    print("Could not import pymongo, not available as a datastore backend")


class Activity(dict):
    pass


_activitydb = {}  # type: Mapping[str, List[Activity]]

class ActivityDatastore:
    def __init__(self, storage_method="memory"):
        if storage_method in ["memory", "mongodb"]:
            pass
        else:
            print("Invalid storage method")

        self.storage_method = storage_method

        if self.storage_method == "mongodb":
            self.client = pymongo.MongoClient()
            self.db = self.client["actwa_server"]
            self.activities = self.db.activities

    def insert(self, activity_type, activity):
        activity["type"] = activity_type
        if self.storage_method == "memory":
            if activity_type not in _activitydb:
                _activitydb[activity_type] = []
            _activitydb[activity_type].append(activity)
        elif self.storage_method == "mongodb":
            self.activities.insert_one(activity)

    def get(self, activity_type):
        if self.storage_method == "memory":
            return _activitydb[activity_type] if activity_type in _activitydb else []
        elif self.storage_method == "mongodb":
            return list(self.activities.find({"type": activity_type}, {"_id": 0}))


