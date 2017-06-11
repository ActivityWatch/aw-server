from typing import Dict
from datetime import datetime, timezone
import json

from flask import request, Blueprint
from flask_restplus import Api, Resource, fields
import iso8601

from aw_core.models import Event
from aw_core import transforms, views, schema
from aw_core.log import get_log_file_path
from aw_core.query import QueryException

from . import app, logger
from .exceptions import BadRequest


# SECURITY
# As we work our way through features, disable (while this is False, we should only accept connections from localhost)
SECURITY_ENABLED = False

# For the planned zeroknowledge storage feature
ZEROKNOWLEDGE_ENABLED = False

blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, doc='/')

app.register_blueprint(blueprint)
app.api  # type: api.ServerAPI


class AnyJson(fields.Raw):
    def format(self, value):
        if type(value) == dict:
            return value
        else:
            return json.loads(value)


# Loads event schema from JSONSchema in aw_core
event = api.schema_model('Event', schema.get_json_schema("event"))

# TODO: Construct all the models from JSONSchema?
#       A downside to contructing from JSONSchema: flask-restplus does not have marshalling support
info = api.model('Info', {
    'hostname': fields.String(),
    'testing': fields.Boolean(),
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


# SERVER INFO

@api.route("/0/info/")
class InfoResource(Resource):
    @api.marshal_with(info)
    def get(self) -> Dict[str, Dict]:
        """Lists info about the aw-server."""
        return app.api.get_info()


# BUCKETS

@api.route("/0/buckets/")
class BucketsResource(Resource):
    # TODO: Add response marshalling/validation
    def get(self) -> Dict[str, Dict]:
        return app.api.get_buckets()


@api.route("/0/buckets/<string:bucket_id>")
class BucketResource(Resource):
    @api.marshal_with(bucket)
    def get(self, bucket_id):
        """Get metadata about bucket."""
        return app.api.get_bucket_metadata(bucket_id)

    @api.expect(create_bucket)
    def post(self, bucket_id):
        """Create bucket."""
        app.api.create_bucket(bucket_id, **request.get_json())
        return {}, 200

    def delete(self, bucket_id):
        app.api.delete_bucket(bucket_id)
        return {}, 200


# EVENTS

@api.route("/0/buckets/<string:bucket_id>/events")
class EventResource(Resource):
    # For some reason this doesn't work with the JSONSchema variant
    # Marshalling doesn't work with JSONSchema events
    # @api.marshal_list_with(event)
    @api.doc(model=event)
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    def get(self, bucket_id):
        """Get events from a bucket"""
        args = request.args
        limit = int(args["limit"]) if "limit" in args else 100
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        events = app.api.get_events(bucket_id, limit=limit, start=start, end=end)
        return events, 200

    # TODO: How to tell expect that it could be a list of events? Until then we can't use validate.
    @api.expect(event)
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

        app.api.create_events(events)
        return {}, 200


# DEPRECATED
@api.route("/0/buckets/<string:bucket_id>/events/replace_last")
class ReplaceLastEventResource(Resource):
    @api.expect(event, validate=True)
    def post(self, bucket_id):
        """Replace last event inserted into the bucket"""
        event = Event(**request.get_json())
        logger.debug("Received {} for event in bucket '{}' with\n\ttimestamp: {}\n\tdata: {}".format(
                     self.__class__.__name__, bucket_id, event.timestamp, event.data))

        app.db[bucket_id].replace_last(event)
        return {}, 200


@api.route("/0/buckets/<string:bucket_id>/heartbeat")
class HeartbeatResource(Resource):
    @api.expect(event, validate=True)
    @api.param("pulsetime", "Largest timewindow allowed between heartbeats for them to merge")
    def post(self, bucket_id):
        """Where heartbeats are sent."""
        heartbeat = Event(**request.get_json())

        if "pulsetime" in request.args:
            pulsetime = float(request.args["pulsetime"])
        else:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        event = app.api.heartbeat(bucket_id, heartbeat, pulsetime)
        return event.to_json_dict(), 200


# VIEWS

@api.route("/0/views/")
class ViewListResource(Resource):
    def get(self):
        """Returns a dict {viewname: view}"""
        viewdict = {viewname: views.get_view(viewname) for viewname in views.get_views}
        return viewdict, 200


@api.route("/0/views/<string:viewname>")
class ViewResource(Resource):
    @api.param("start", "Start datetime of events to query over")
    @api.param("end", "End datetime of events to query over")
    def get(self, viewname):
        """Executes a view query and returns the result"""
        args = request.args
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        result = app.api.query_view(viewname, start, end)
        return result, 200

    @api.expect(view)
    def post(self, viewname):
        """Creates a view"""
        view = request.get_json()
        app.api.create_view(viewname, view)
        return {}, 200


# LOGGING

@api.route("/0/log")
class LogResource(Resource):
    @api.expect()
    def get(self):
        """Get the server log in json format"""
        return app.api.get_log(), 200
