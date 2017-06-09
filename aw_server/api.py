from typing import Dict
from datetime import datetime, timezone
from socket import gethostname
import functools
import json

from flask import request, Blueprint
from flask_restplus import Api, Resource, fields
import werkzeug.exceptions
import iso8601

from aw_core.models import Event
from aw_core import transforms, views, schema
from . import app, logger
from aw_core.log import get_log_file_path
from aw_core.query import QueryException


# SECURITY
# As we work our way through features, disable (while this is False, we should only accept connections from localhost)
SECURITY_ENABLED = False

# For the planned zeroknowledge storage feature
ZEROKNOWLEDGE_ENABLED = False

blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, doc='/')

app.register_blueprint(blueprint)


def check_bucket_exists(f):
    @functools.wraps(f)
    def g(self, bucket_id, *args, **kwargs):
        if bucket_id not in app.db.buckets():
            raise BadRequest("NoSuchBucket", "There's no bucket named {}".format(bucket_id))
        f(self, bucket_id, *args, **kwargs)
    return g


def check_view_exists(f):
    @functools.wraps(f)
    def g(self, view_id, *args, **kwargs):
        if view_id not in views.get_views():
            raise BadRequest("NoSuchView", "There's no view named {}".format(view_id))
        f(self, view_id, *args, **kwargs)
    return g


class AnyJson(fields.Raw):
    def format(self, value):
        if type(value) == dict:
            return value
        else:
            return json.loads(value)

# TODO: Construct from JSONSchema
info = api.model('Info', {
    'hostname': fields.String(),
    'testing': fields.Boolean(),
})

# Loads event schema from JSONSchema in aw_core
event = api.schema_model('Event', schema.get_json_schema("event"))

# TODO: Construct from JSONSchema
bucket = api.model('Bucket', {
    'id': fields.String(required=True, description='The buckets unique id'),
    'name': fields.String(required=False, description='The buckets readable and renameable name'),
    'type': fields.String(required=True, description='The buckets event type'),
    'client': fields.String(required=True, description='The name of the watcher client'),
    'hostname': fields.String(required=True, description='The hostname of the client that the bucket belongs to'),
    'created': fields.DateTime(required=True, description='The creation datetime of the bucket'),
})

# TODO: Construct from JSONSchema
create_bucket = api.model('CreateBucket', {
    'client': fields.String(required=True),
    'type': fields.String(required=True),
    'hostname': fields.String(required=True),
})

# TODO: Construct from JSONSchema
view = api.model('View', {
    'name': fields.String,
    'created': fields.DateTime,
    'query': AnyJson,  # Can be any dict
})


class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type, message):
        super().__init__(message)
        self.type = type


@api.route("/0/info/")
class InfoResource(Resource):
    """
    Lists info about the aw-server.
    """

    @api.marshal_with(info)
    def get(self) -> Dict[str, Dict]:
        payload = {
            'hostname': gethostname(),
            'testing': app.config['DEBUG']  # Checks if flask is run in debug mode, which it will depending on if it is in testing mode or not
                                            # FIXME: The above is no longer true, the testing bool should be stored in the app object.
        }
        return payload


"""
    BUCKETS
"""


@api.route("/0/buckets/")
class BucketsResource(Resource):
    """
    Used to list buckets.
    """

    def get(self) -> Dict[str, Dict]:
        """
        Get dict {bucket_name: Bucket} of all buckets
        """
        logger.debug("Received get request for buckets")
        buckets = app.db.buckets()
        for b in buckets:
            last_events = app.db[b].get(limit=1)
            if len(last_events) > 0:
                last_event = last_events[0]
                last_updated = last_event.timestamp + last_event.duration
                buckets[b]["last_updated"] = last_updated.isoformat()
        return buckets


@api.route("/0/buckets/<string:bucket_id>")
class BucketResource(Resource):
    """Used to get metadata about buckets and create them."""

    @check_bucket_exists
    @api.marshal_with(bucket)
    def get(self, bucket_id):
        """Get metadata about bucket."""
        bucket = app.db[bucket_id]
        return bucket.metadata()

    @api.expect(create_bucket)
    def post(self, bucket_id):
        """Create bucket."""
        data = request.get_json()
        if bucket_id in app.db.buckets():
            raise BadRequest("BucketExists", "A bucket with this name already exists, cannot create it")
        app.db.create_bucket(
            bucket_id,
            type=data["type"],
            client=data["client"],
            hostname=data["hostname"],
            created=datetime.now()
        )
        return {}, 200

    def delete(self, bucket_id):
        """Delete a bucket (only possible when run in testing mode)"""
        testing = app.config['DEBUG']
        if not testing:
            msg = "Deleting buckets is only permitted if aw-server is running in testing mode"
            raise BadRequest("PermissionDenied", msg)

        if bucket_id not in app.db.buckets():
            msg = "There's no bucket named {}".format(bucket_id)
            raise BadRequest("NoSuchBucket", msg)

        app.db.delete_bucket(bucket_id)
        logger.warning("Deleted bucket '{}'".format(bucket_id))
        return {}, 200


"""
    EVENTS
"""


@api.route("/0/buckets/<string:bucket_id>/events")
class EventResource(Resource):
    """Used to get and create events in a particular bucket."""

    @check_bucket_exists
    @api.marshal_list_with(event)
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    def get(self, bucket_id):
        """
        Get events from a bucket
        """
        args = request.args
        limit = int(args["limit"]) if "limit" in args else 100
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        logger.debug("Received get request for events in bucket '{}'".format(bucket_id))
        events = [event.to_json_dict() for event in app.db[bucket_id].get(limit, start, end)]
        return events

    @check_bucket_exists
    @api.expect(event)  # TODO: How to tell expect that it could be a list of events? Until then we can't use validate.
    def post(self, bucket_id):
        """Create events for a bucket. Can handle both single events and multiple ones."""
        data = request.get_json()
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, data))

        if isinstance(data, dict):
            events = [Event(**data)]
        elif isinstance(data, list):
            events = [Event(**e) for e in data]
        else:
            raise BadRequest("Invalid POST data", "")

        app.db[bucket_id].insert(events)
        return {}, 200


# DEPRECATED
@api.route("/0/buckets/<string:bucket_id>/events/replace_last")
class ReplaceLastEventResource(Resource):
    """Replaces last event inserted into bucket"""

    @check_bucket_exists
    @api.expect(event, validate=True)
    def post(self, bucket_id):
        """Replace last event inserted into the bucket"""
        event = Event(**request.get_json())
        logger.debug("Received {} for event in bucket '{}' with\n\ttimestamp: {}\n\tdata: {}".format(
                     self.__class__.__name__, bucket_id, event.timestamp, event.data))

        app.db[bucket_id].replace_last(event)
        return {}, 200


# TODO: Could this be used in place of api.param and api.expect in heartbeat?
heartbeat_parser = api.parser()
heartbeat_parser.add_argument('event', type=event, help='The heartbeat event', location="json", required=True)
heartbeat_parser.add_argument('pulsetime', type=float, help='The maximum time allowed between heartbeats', location='args', required=True)


@api.route("/0/buckets/<string:bucket_id>/heartbeat")
class HeartbeatResource(Resource):
    """
    Heartbeats are useful when implementing watchers that simply keep
    track of a state, how long it's in that state and when it changes.

    Heartbeats are essentially events without durations.

    If the heartbeat was identical to the last (apart from timestamp), then the last event has its duration updated.
    If the heartbeat differed, then a new event is created.

    Such as:
     - Active application and window title (aw-watcher-window)
     - Active browser tab (aw-watcher-web)
     - Currently open document (wakatime)

    Might be badly suited for:
     - Has activity occurred? (aw-watcher-afk)
       Edit: Not anymore, aw-watcher-afk has now been rewritten to use heartbeats.

    Inspired by: https://wakatime.com/developers#heartbeats
    """

    # TODO: We *really* need integration tests for all this.
    # TODO: Try using heartbeat_parser for param validation (can it also validate Event?)
    @check_bucket_exists
    @api.expect(event, validate=True)
    @api.param("pulsetime", "Largest timewindow allowed between heartbeats for them to merge")
    def post(self, bucket_id):
        """Where heartbeats are sent."""
        heartbeat = Event(**request.get_json())

        if "pulsetime" in request.args:
            pulsetime = float(request.args["pulsetime"])
        else:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        logger.debug("Received heartbeat in bucket '{}' with\n\ttimestamp: {}\n\tdata: {}".format(bucket_id, heartbeat.timestamp, heartbeat.data))

        # The endtime here is set such that in the event that the heartbeat is older than an
        # existing event we should try to merge it with the last event before the heartbeat instead.
        # FIXME: This gets rid of the "heartbeat was older than last event"-type warning and
        #        also causes any already existing "newer" events to be overwritten in the
        #        replace_last call below.
        events = app.db[bucket_id].get(limit=3, endtime=heartbeat.timestamp)

        # FIXME: The below is needed due to the weird fact that for some reason
        # events[0] turns out to be the *oldest* event,
        # events[1] turns out to be the latest,
        # events[2] the second latest, etc.
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        # Uncomment this to verify my above claim:
        #  for e in events:
        #      print(e.timestamp)
        #      print(e.labels)

        if len(events) >= 1:
            last_event = events[0]
            merged = transforms.heartbeat_merge(last_event, heartbeat, pulsetime)
            if merged is not None:
                # Heartbeat was merged into last_event
                app.db[bucket_id].replace_last(merged)
                return merged.to_json_dict(), 200

        # Heartbeat should be stored as new event
        logger.debug("last event either didn't have identical labels, was too old or didn't exist. heartbeat will be stored as new event")
        app.db[bucket_id].insert(heartbeat)
        return heartbeat.to_json_dict(), 200


"""
    VIEWS
"""


@api.route("/0/views/")
class ViewListResource(Resource):
    def get(self):
        """Retuns names of all views"""
        return views.get_views(), 200


@api.route("/0/views/<string:viewname>")
class QueryViewResource(Resource):

    @check_view_exists
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    def get(self, viewname):
        """Executes a view query and returns the result"""
        args = request.args
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        try:
            result = views.query_view(viewname, app.db, start, end)
        except QueryException as qe:
            return {"msg": str(qe)}, 500
        return result, 200

    @api.expect(view)
    def post(self, viewname):
        """Creates a view"""
        view = request.get_json()
        view["name"] = viewname
        if "created" not in view:
            view["created"] = datetime.now(timezone.utc).isoformat()
        views.create_view(view)
        return {}, 200


@api.route("/0/views/<string:viewname>/info")
class InfoViewResource(Resource):
    """
        Sends information about the specified view
    """

    @check_view_exists
    def get(self, viewname):
        return views.get_view(viewname), 200


"""
    LOGGING
"""


@api.route("/0/log")
class LogResource(Resource):
    """Server log of the current instance in json format"""

    @api.expect()
    def get(self):
        """Get the server log in json format"""
        payload = []
        with open(get_log_file_path(), 'r') as log_file:
            for line in log_file.readlines()[::-1]:
                payload.append(json.loads(line))
        return payload, 200
