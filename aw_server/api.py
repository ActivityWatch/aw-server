from typing import Dict, List, Any
from datetime import datetime, timezone
from socket import gethostname
import functools
import json
import logging

from aw_core.models import Event
from aw_core import transforms, views
from aw_core.log import get_log_file_path
from aw_core.query import QueryException

from .exceptions import BadRequest


logger = logging.getLogger(__name__)


def check_bucket_exists(f):
    @functools.wraps(f)
    def g(self, bucket_id, *args, **kwargs):
        if bucket_id not in self.db.buckets():
            raise BadRequest("NoSuchBucket", "There's no bucket named {}".format(bucket_id))
        return f(self, bucket_id, *args, **kwargs)
    return g


def check_view_exists(f):
    @functools.wraps(f)
    def g(self, view_id, *args, **kwargs):
        if view_id not in views.get_views():
            raise BadRequest("NoSuchView", "There's no view named {}".format(view_id))
        return f(self, view_id, *args, **kwargs)
    return g


class ServerAPI:
    def __init__(self, db, testing):
        self.db = db
        self.testing = testing

    def get_info(self) -> Dict[str, Dict]:
        """Get server info"""
        payload = {
            'hostname': gethostname(),
            'testing': self.testing
        }
        return payload

    def get_buckets(self) -> Dict[str, Dict]:
        """Get dict {bucket_name: Bucket} of all buckets"""
        logger.debug("Received get request for buckets")
        buckets = self.db.buckets()
        for b in buckets:
            last_events = self.db[b].get(limit=1)
            if len(last_events) > 0:
                last_event = last_events[0]
                last_updated = last_event.timestamp + last_event.duration
                buckets[b]["last_updated"] = last_updated.isoformat()
        return buckets

    @check_bucket_exists
    def get_bucket_metadata(self, bucket_id: str) -> Dict[str, Any]:
        """Get metadata about bucket."""
        bucket = self.db[bucket_id]
        return bucket.metadata()

    def create_bucket(self, bucket_id: str, bucket_type: str, client: str, hostname: str) -> None:
        """Create bucket."""
        if bucket_id in self.db.buckets():
            raise BadRequest("BucketExists", "A bucket with this name already exists, cannot create it")
        self.db.create_bucket(
            bucket_id,
            type=bucket_type,
            client=client,
            hostname=hostname,
            created=datetime.now()
        )
        return None

    @check_bucket_exists
    def delete_bucket(self, bucket_id: str) -> None:
        """Delete a bucket (only possible when run in testing mode)"""
        if not self.testing:
            msg = "Deleting buckets is only permitted if aw-server is running in testing mode"
            raise BadRequest("PermissionDenied", msg)

        self.db.delete_bucket(bucket_id)
        logger.debug("Deleted bucket '{}'".format(bucket_id))
        return None

    @check_bucket_exists
    def get_events(self, bucket_id: str, limit: int = 100,
                   start: datetime = None, end: datetime = None) -> List[Event]:
        """Get events from a bucket"""
        logger.debug("Received get request for events in bucket '{}'".format(bucket_id))
        events = [event.to_json_dict() for event in
                  self.db[bucket_id].get(limit, start, end)]
        return events

    @check_bucket_exists
    def create_events(self, bucket_id: str, events: List[Event]):
        """Create events for a bucket. Can handle both single events and multiple ones."""
        self.db[bucket_id].insert(events)
        return None

    @check_bucket_exists
    def heartbeat(self, bucket_id: str, heartbeat: Event, pulsetime: float) -> Event:
        """
        Heartbeats are useful when implementing watchers that simply keep
        track of a state, how long it's in that state and when it changes.

        Heartbeats are essentially events without durations.

        If the heartbeat was identical to the last (apart from timestamp), then the last event has its duration updated.
        If the heartbeat differed, then a new event is created.

        Such as:
         - Active application and window title
           - Example: aw-watcher-window
         - Currently open document/browser tab/playing song
           - Example: wakatime
           - Example: aw-watcher-web
           - Example: aw-watcher-spotify
         - Is the user active/inactive?
           Send an event on some interval indicating if the user is active or not.
           - Example: aw-watcher-afk

        Inspired by: https://wakatime.com/developers#heartbeats
        """
        logger.debug("Received heartbeat in bucket '{}'\n\ttimestamp: {}\n\tdata: {}".format(
                     bucket_id, heartbeat.timestamp, heartbeat.data))

        # The endtime here is set such that in the event that the heartbeat is older than an
        # existing event we should try to merge it with the last event before the heartbeat instead.
        # FIXME: This gets rid of the "heartbeat was older than last event"-type warning and
        #        also causes any already existing "newer" events to be overwritten in the
        #        replace_last call below.
        events = self.db[bucket_id].get(limit=1, endtime=heartbeat.timestamp)

        if len(events) >= 1:
            last_event = events[0]
            merged = transforms.heartbeat_merge(last_event, heartbeat, pulsetime)
            if merged is not None:
                # Heartbeat was merged into last_event
                self.db[bucket_id].replace_last(merged)
                return merged

        # Heartbeat should be stored as new event
        logger.info("Received heartbeat which was much newer than the last, creating as a new event.")
        self.db[bucket_id].insert(heartbeat)
        return heartbeat

    def get_views(self) -> Dict[str, dict]:
        """Returns a dict {viewname: view}"""
        return {viewname: views.get_view(viewname) for viewname in views.get_views}

    # TODO: start and end should probably be the last day if None is given
    @check_view_exists
    def query_view(self, viewname, start: datetime = None, end: datetime = None):
        """Executes a view query and returns the result"""
        try:
            result = views.query_view(viewname, self.db, start, end)
        except QueryException as qe:
            raise BadRequest("QueryError", "Query error: {}".format(str(qe)))
        return result

    def create_view(self, viewname: str, view: dict):
        """Creates a view"""
        view["name"] = viewname
        if "created" not in view:
            view["created"] = datetime.now(timezone.utc).isoformat()
        views.create_view(view)

    # TODO: Right now the log format on disk has to be JSON, this is hard to read by humans...
    def get_log(self):
        """Get the server log in json format"""
        payload = []
        with open(get_log_file_path(), 'r') as log_file:
            for line in log_file.readlines()[::-1]:
                payload.append(json.loads(line))
        return payload, 200
