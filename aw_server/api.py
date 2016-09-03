from typing import List, Dict
from datetime import datetime, timedelta
import binascii
import os
import json
import iso8601
import werkzeug.exceptions

from flask import request, Blueprint
from flask_restplus import Api, Resource, fields

from aw_core.models import Event
from aw_core import transforms, views
from . import app, logger
from .log import get_log_file_path


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
    'unit': fields.String,
    'value': fields.Float,
})

event = api.model('Event', {
    'timestamp': fields.List(fields.DateTime(required=True)),
    # Duration validation is broken
    #'duration': fields.List(fields.Nested(fDuration)),
    'count': fields.List(fields.Integer()),
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

view = api.model('View',{
    'name': fields.String,
    'created': fields.DateTime,
    'query': AnyJson,  # Can be any dict
})

class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type, message):
        super().__init__(message)
        self.type = type


"""

    BUCKETS

"""


@api.route("/0/buckets")
class BucketsResource(Resource):
    """
    Used to list buckets.
    """

    def get(self):
        """
        Get list of all buckets
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
        return app.db[bucket_id].metadata()

    @api.expect(create_bucket)
    def post(self, bucket_id):
        """
        Create bucktet
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

    #@api.marshal_list_with(event)
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

        if bucket_id not in app.db.buckets():
            msg = "Unable to fetch data from bucket {}, because it doesn't exist".format(bucket_id)
            logger.error(msg)
            raise BadRequest("NoSuchBucket", msg)

        logger.debug("Received get request for events in bucket '{}'".format(bucket_id))
        return app.db[bucket_id].get(limit, start, end)

    @api.expect(event)
    def post(self, bucket_id):
        """
        Create events for a bucket
        """
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, request.get_json()))
        data = request.get_json()
        events = []
        if isinstance(data, dict):
            events = [Event(**data)]
        elif isinstance(data, list):
            for e in data:
                events.append(Event(**e))
        else:
            logger.error("Invalid JSON object")
            raise BadRequest("InvalidJSON", "Invalid JSON object")
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

        if bucket_id not in app.db.buckets():
            msg = "Unable to fetch data from bucket {}, because it doesn't exist".format(bucket_id)
            logger.error(msg)
            raise BadRequest("NoSuchBucket", msg)

        logger.debug("Received chunk request for bucket '{}' between '{}' and '{}'".format(bucket_id, start, end))
        events = app.db[bucket_id].get(start, end)
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
        data = request.get_json()
        if isinstance(data, dict):
            app.db[bucket_id].replace_last(Event(**data))
        else:
            logger.error("Invalid JSON object")
            raise BadRequest("InvalidJSON", "Invalid JSON object")
        return {}, 200


"""

    VIEWS

"""


@api.route("/0/views")
class ViewListResource(Resource):
    """
    """

    def get(self):
        """
        """
        return views.get_views(), 200


@api.route("/0/views/<string:viewname>")
class QueryViewResource(Resource):
    """
    """

    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    def get(self, viewname):
        """
        """
        if viewname not in views.views:
            return {}, 404
        args = request.args
        limit = int(args["limit"]) if "limit" in args else -1
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None
        
        result = views.query_view(viewname, app.db, limit, start, end)
        return result, 200


@api.route("/0/views/<string:viewname>/info")
class InfoViewResource(Resource):
    """
    """

    def get(self, viewname):
        return views.get_view(viewname), 200


@api.route("/0/views/<string:viewname>/create")
class CreateViewResource(Resource):
    """
    """

    @api.expect(view)
    def post(self, viewname):
        view = request.get_json()
        view["name"] = viewname
        if "created" not in view:
            view["created"] = datetime.now(timezone.utc).isoformat()
        views.views[viewname] = view
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
