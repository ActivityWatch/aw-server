from typing import Dict
from datetime import datetime, timezone
import json
import iso8601
import werkzeug.exceptions

from flask import request, Blueprint
from flask_restplus import Api, Resource, fields

from aw_core.models import Event
from aw_core import transforms, views
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


class AnyJson(fields.Raw):
    def format(self, value):
        return json.loads(value)

# TODO: Move to aw_core.models, construct from JSONSchema (if reasonably straight-forward)

fDuration = api.model('Duration', {
    'value': fields.Float(),
    'unit': fields.String(),
})

event = api.model('Event', {
    'timestamp': fields.List(fields.DateTime(required=True)),
    'duration': fields.List(fields.Nested(fDuration)),
    'count': fields.List(fields.Integer()),
    'label': fields.List(fields.String(description='Labels on event'))
})

heartbeat = api.model('Event', {
    'timestamp': fields.List(fields.DateTime(required=True)),
    'label': fields.List(fields.String(description='Labels on event'))
})

bucket = api.model('Bucket', {
    'id': fields.String(required=True, description='The buckets unique id'),
    'name': fields.String(required=False, description='The buckets readable and renameable name'),
    'type': fields.String(required=True, description='The buckets event type'),
    'client': fields.String(required=True, description='The name of the watcher client'),
    'hostname': fields.String(required=True, description='The hostname of the client that the bucket belongs to'),
    'created': fields.DateTime(required=True, description='The creation datetime of the bucket'),
})

create_bucket = api.model('CreateBucket', {
    'client': fields.String(required=True),
    'type': fields.String(required=True),
    'hostname': fields.String(required=True),
})

view = api.model('View', {
    'name': fields.String,
    'created': fields.DateTime,
    'query': AnyJson,  # Can be any dict
})


class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type, message):
        super().__init__(message)
        self.type = type


def checkBucketExists(bucket_id):
    if bucket_id not in app.db.buckets():
        # FIXME: Really ugly, but should get rid of a lot of errors. We need a better solution for
        # when a client tries to add queued events to a removed bucket. Such as always ensuring the
        # bucket exists at initialization (which ensures the client will work properly again after a restart).
        app.db.create_bucket(bucket_id, type="unknown", client="unknown", hostname="unknown")
        # msg = "Unable to fetch data from bucket {}, because it doesn't exist".format(bucket_id)
        # logger.error(msg)
        # raise BadRequest("NoSuchBucket", msg)
        # bucketNotFound = "bucket not found", 404


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
        return app.db.buckets()


@api.route("/0/buckets/<string:bucket_id>")
class BucketResource(Resource):
    """
    Used to get metadata about buckets and create them.
    """

    @api.marshal_with(bucket)
    def get(self, bucket_id):
        """
        Get metadata about bucket
        """
        logger.debug("Received get request for bucket '{}'".format(bucket_id))

        try:
            bucket = app.db[bucket_id]
            return bucket.metadata()
        except KeyError:
            return "bucket with id not found", 404

    @api.expect(create_bucket)
    def post(self, bucket_id):
        """
        Create bucket
        """
        data = request.get_json()
        if bucket_id in app.db.buckets():
            raise BadRequest("BucketAlreadyExists", "A bucket with this name already exists, cannot create it")
        app.db.create_bucket(
            bucket_id,
            type=data["type"],
            client=data["client"],
            hostname=data["hostname"],
            created=datetime.now()
        )
        return {}, 200


"""

    EVENTS

"""


@api.route("/0/buckets/<string:bucket_id>/events")
class EventResource(Resource):
    """
    Used to get and create events in a particular bucket.
    """

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

        checkBucketExists(bucket_id)

        logger.debug("Received get request for events in bucket '{}'".format(bucket_id))
        events = [event.to_json_dict() for event in app.db[bucket_id].get(limit, start, end)]
        return events

    @api.expect(event)
    def post(self, bucket_id):
        """
        Create events for a bucket
        """
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, request.get_json()))

        checkBucketExists(bucket_id)

        data = request.get_json()
        events = Event.from_json_obj(data)
        app.db[bucket_id].insert(events)
        return {}, 200


@api.route("/0/buckets/<string:bucket_id>/events/chunk")
class EventChunkResource(Resource):
    """
    Used to get chunked events
    """

    @api.param("start", "Start date of chunk")
    @api.param("end", "End date of chunk")
    def get(self, bucket_id):
        """
        Get chunked events from a bucket
        """
        args = request.args
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        checkBucketExists(bucket_id)

        logger.debug("Received chunk request for bucket '{}' between '{}' and '{}'".format(bucket_id, start, end))
        events = app.db[bucket_id].get(-1, start, end)
        return transforms.chunk(events)


@api.route("/0/buckets/<string:bucket_id>/events/replace_last")
class ReplaceLastEventResource(Resource):
    """
    Replaces last event inserted into bucket
    """

    @api.expect(event)
    def post(self, bucket_id):
        """
        Replace last event inserted into the bucket
        """
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, request.get_json()))

        checkBucketExists(bucket_id)
        data = request.get_json()

        if not isinstance(data, dict):
            logger.error("Invalid JSON object")
            raise BadRequest("InvalidJSON", "Invalid JSON object")

        app.db[bucket_id].replace_last(Event(**data))
        return {}, 200


@api.route("/0/buckets/<string:bucket_id>/heartbeat")
class HeartbeatResource(Resource):
    """
    Heartbeats are useful when implementing watchers that simply keep
    track of a state, when it's a certain value and when it changes.

    Heartbeats are essentially events without durations.

    If the heartbeat was identical to the last (apart from timestamp), then the last event has its duration updated.
    If the heartbeat differed, then a new event is created.

    Such as:
     - Active application and window title (aw-watcher-window)
     - Active browser tab (aw-watcher-web)
     - Currently open document (wakatime)

    Might be badly suited for:
     - Has activity occurred? (aw-watcher-afk)

    Inspired by: https://wakatime.com/developers#heartbeats
    """

    @api.expect(heartbeat)
    @api.param("pulsetime", "Largest timewindow allowed between heartbeats for them to merge")
    def post(self, bucket_id):
        """
        Where heartbeats are sent.
        """
        logger.debug("Received post request for heartbeat in bucket '{}' and data: {}".format(bucket_id, request.get_json()))

        checkBucketExists(bucket_id)
        if "pulsetime" not in request.args:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        data = request.get_json()
        pulsetime = float(request.args["pulsetime"])

        if not isinstance(data, dict):
            logger.error("Invalid JSON object")
            raise BadRequest("InvalidJSON", "Invalid JSON object")

        heartbeat = Event(**data)
        events = app.db[bucket_id].get(limit=1)

        if len(events) == 1:
            print("found a last event")
            last_event = events[0]

            # Diff between timestamps in seconds, takes into account the duration of the last event
            ts_diff_seconds = (heartbeat.timestamp - last_event.timestamp).total_seconds()
            last_duration_seconds = last_event.duration.total_seconds() if last_event.duration else 0

            if last_event.labels == heartbeat.labels and ts_diff_seconds < pulsetime + last_duration_seconds:
                last_event.duration = {"value": ts_diff_seconds, "unit": "s"}

                app.db[bucket_id].replace_last(last_event)
                return last_event.to_json_dict(), 200

        print("last event either didn't exist, didn't have identical labels or was too old. heartbeat will be stored as new event")
        app.db[bucket_id].insert(heartbeat)
        return heartbeat.to_json_dict(), 200


"""

    VIEWS

"""


@api.route("/0/views/")
class ViewListResource(Resource):
    def get(self):
        """
            Retuns names of all views
        """
        return views.get_views(), 200


@api.route("/0/views/<string:viewname>")
class QueryViewResource(Resource):
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    def get(self, viewname):
        """
            Executes a view query and returns the result
        """
        if viewname not in views.views:
            return {"msg": "There's no view with the name '{}'".format(viewname)}, 404
        args = request.args
        limit = int(args["limit"]) if "limit" in args else -1
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        try:
            result = views.query_view(viewname, app.db, limit, start, end)
        except QueryException as qe:
            return {"msg": str(qe)}, 500
        return result, 200


@api.route("/0/views/<string:viewname>/info")
class InfoViewResource(Resource):
    """
        Sends information about the specified view
    """

    def get(self, viewname):
        if viewname not in views.views:
            return {"msg": "There's no view with the name '{}'".format(viewname)}, 404
        return views.get_view(viewname), 200


@api.route("/0/views/<string:viewname>/create")
class CreateViewResource(Resource):
    """
        Creates a view
    """
    @api.expect(view)
    def post(self, viewname):
        view = request.get_json()
        view["name"] = viewname
        if "created" not in view:
            view["created"] = datetime.now(timezone.utc).isoformat()
        views.create_view(view)
        return {}, 200


"""

    LOGGING

"""


@api.route("/0/log")
class LogResource(Resource):
    """
    Server log of the current instance in json format
    """

    @api.expect()
    def get(self):
        """
        Get the server log in json format
        """
        payload = []
        with open(get_log_file_path(), 'r') as log_file:
            for line in log_file.readlines()[::-1]:
                payload.append(json.loads(line))
        return payload, 200
