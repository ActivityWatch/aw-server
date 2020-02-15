from typing import Dict
import traceback
import json

from flask import request, Blueprint, jsonify, current_app, make_response
from flask_restx import Api, Resource, fields
import iso8601
from datetime import datetime, timedelta

from aw_core import schema
from aw_core.models import Event
from aw_query.exceptions import QueryException

from . import logger
from .api import ServerAPI
from .exceptions import BadRequest, Unauthorized


# SECURITY
# As we work our way through features, disable (while this is False, we should only accept connections from localhost)
SECURITY_ENABLED = False

# For the planned zeroknowledge storage feature
ZEROKNOWLEDGE_ENABLED = False

blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, doc='/')


# TODO: Clean up JSONEncoder code?
# Move to server.py
class CustomJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def default(self, obj, *args, **kwargs):
        try:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, timedelta):
                return obj.total_seconds()
        except TypeError:
            pass
        return json.JSONEncoder.default(self, obj)


class AnyJson(fields.Raw):
    def format(self, value):
        if type(value) == dict:
            return value
        else:
            return json.loads(value)


# Loads event and bucket schema from JSONSchema in aw_core
event = api.schema_model('Event', schema.get_json_schema("event"))
bucket = api.schema_model('Bucket', schema.get_json_schema("bucket"))
buckets_export = api.schema_model('Export', schema.get_json_schema("export"))

# TODO: Construct all the models from JSONSchema?
#       A downside to contructing from JSONSchema: flask-restplus does not have marshalling support

info = api.model('Info', {
    'hostname': fields.String(),
    'version': fields.String(),
    'testing': fields.Boolean(),
    'device_id': fields.String(),
})

create_bucket = api.model('CreateBucket', {
    'client': fields.String(required=True),
    'type': fields.String(required=True),
    'hostname': fields.String(required=True),
})

query = api.model('Query', {
    'timeperiods': fields.List(fields.String, required=True, description='List of periods to query'),
    'query': fields.List(fields.String, required=True, description='String list of query statements'),
})


def copy_doc(api_method):
    """Decorator that copies another functions docstring to the decorated function.
       Used to copy the docstrings in ServerAPI over to the flask-restplus Resources.
       (The copied docstrings are then used by flask-restplus/swagger)"""
    def decorator(f):
        f.__doc__ = api_method.__doc__
        return f
    return decorator


# SERVER INFO

@api.route("/0/info")
class InfoResource(Resource):
    @api.marshal_with(info)
    @copy_doc(ServerAPI.get_info)
    def get(self) -> Dict[str, Dict]:
        return current_app.api.get_info()


# BUCKETS

@api.route("/0/buckets/")
class BucketsResource(Resource):
    # TODO: Add response marshalling/validation
    @copy_doc(ServerAPI.get_buckets)
    def get(self) -> Dict[str, Dict]:
        return current_app.api.get_buckets()


@api.route("/0/buckets/<string:bucket_id>")
class BucketResource(Resource):
    @api.doc(model=bucket)
    @copy_doc(ServerAPI.get_bucket_metadata)
    def get(self, bucket_id):
        return current_app.api.get_bucket_metadata(bucket_id)

    @api.expect(create_bucket)
    @copy_doc(ServerAPI.create_bucket)
    def post(self, bucket_id):
        data = request.get_json()
        bucket_created = current_app.api.create_bucket(bucket_id, event_type=data["type"], client=data["client"], hostname=data["hostname"])
        if bucket_created:
            return {}, 200
        else:
            return {}, 304

    @copy_doc(ServerAPI.delete_bucket)
    @api.param("force", "Needs to be =1 to delete a bucket it non-testing mode")
    def delete(self, bucket_id):
        args = request.args
        if not current_app.api.testing:
            if "force" not in args or args["force"] != "1":
                msg = "Deleting buckets is only permitted if aw-server is running in testing mode or if ?force=1"
                raise Unauthorized("DeleteBucketUnauthorized", msg)

        current_app.api.delete_bucket(bucket_id)
        return {}, 200


# EVENTS

@api.route("/0/buckets/<string:bucket_id>/events")
class EventsResource(Resource):
    # For some reason this doesn't work with the JSONSchema variant
    # Marshalling doesn't work with JSONSchema events
    # @api.marshal_list_with(event)
    @api.doc(model=event)
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    @copy_doc(ServerAPI.get_events)
    def get(self, bucket_id):
        args = request.args
        limit = int(args["limit"]) if "limit" in args else -1
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        events = current_app.api.get_events(bucket_id, limit=limit, start=start, end=end)
        return events, 200

    # TODO: How to tell expect that it could be a list of events? Until then we can't use validate.
    @api.expect(event)
    @copy_doc(ServerAPI.create_events)
    def post(self, bucket_id):
        data = request.get_json()
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, data))

        if isinstance(data, dict):
            events = [Event(**data)]
        elif isinstance(data, list):
            events = [Event(**e) for e in data]
        else:
            raise BadRequest("Invalid POST data", "")

        event = current_app.api.create_events(bucket_id, events)
        return event.to_json_dict() if event else None, 200


@api.route("/0/buckets/<string:bucket_id>/events/count")
class EventCountResource(Resource):
    @api.doc(model=fields.Integer)
    @api.param("start", "Start date of eventcount")
    @api.param("end", "End date of eventcount")
    @copy_doc(ServerAPI.get_eventcount)
    def get(self, bucket_id):
        args = request.args
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        events = current_app.api.get_eventcount(bucket_id, start=start, end=end)
        return events, 200


@api.route("/0/buckets/<string:bucket_id>/events/<string:event_id>")
class EventResource(Resource):
    # For some reason this doesn't work with the JSONSchema variant
    # Marshalling doesn't work with JSONSchema events
    # @api.marshal_list_with(event)
    # @api.doc(model=event)
    # @copy_doc(ServerAPI.get_event)
    # def get(self, bucket_id, event_id):
    #     events = current_app.api.get_events(bucket_id, limit=limit, start=start, end=end)
    #     return events, 200

    @copy_doc(ServerAPI.delete_event)
    def delete(self, bucket_id, event_id):
        logger.debug("Received delete request for event with id '{}' in bucket '{}'".format(event_id, bucket_id))
        success = current_app.api.delete_event(bucket_id, event_id)
        return {"success": success}, 200


@api.route("/0/buckets/<string:bucket_id>/heartbeat")
class HeartbeatResource(Resource):
    @api.expect(event, validate=True)
    @api.param("pulsetime", "Largest timewindow allowed between heartbeats for them to merge")
    @copy_doc(ServerAPI.heartbeat)
    def post(self, bucket_id):
        heartbeat = Event(**request.get_json())

        if "pulsetime" in request.args:
            pulsetime = float(request.args["pulsetime"])
        else:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        event = current_app.api.heartbeat(bucket_id, heartbeat, pulsetime)
        return event.to_json_dict(), 200


# QUERY

@api.route("/0/query/")
class QueryResource(Resource):
    # TODO Docs
    @api.expect(query, validate=True)
    @api.param("name", "Name of the query (required if using cache)")
    def post(self):
        name = ""
        if "name" in request.args:
            name = request.args["name"]
        query = request.get_json()
        try:
            result = current_app.api.query2(name, query["query"], query["timeperiods"], False)
            return jsonify(result)
        except QueryException as qe:
            traceback.print_exc()
            return {"type": type(qe).__name__, "message": str(qe)}, 400


# EXPORT AND IMPORT


@api.route("/0/export")
class ExportAllResource(Resource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_all)
    def get(self):
        buckets_export = current_app.api.export_all()
        payload = {"buckets": buckets_export}
        response = make_response(json.dumps(payload))
        filename = "aw-buckets-export.json"
        response.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
        return response


# TODO: Perhaps we don't need this, could be done with a query argument to /0/export instead
@api.route("/0/buckets/<string:bucket_id>/export")
class BucketExportResource(Resource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_bucket)
    def get(self, bucket_id):
        bucket_export = current_app.api.export_bucket(bucket_id)
        payload = {"buckets": {bucket_export["id"]: bucket_export}}
        response = make_response(json.dumps(payload))
        filename = "aw-bucket-export_{}.json".format(bucket_export["id"])
        response.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
        return response


@api.route("/0/import")
class ImportAllResource(Resource):
    @api.expect(buckets_export)
    @copy_doc(ServerAPI.import_all)
    def post(self):
        # If import comes from a form in th web-ui
        if len(request.files) > 0:
            # web-ui form only allows one file, but technically it's possible to
            # upload multiple files at the same time
            for filename, f in request.files.items():
                buckets = json.loads(f.stream.read())["buckets"]
                current_app.api.import_all(buckets)
        # Normal import from body
        else:
            buckets = request.get_json()["buckets"]
            current_app.api.import_all(buckets)
        return None, 200


# LOGGING

@api.route("/0/log")
class LogResource(Resource):
    @copy_doc(ServerAPI.get_log)
    def get(self):
        return current_app.api.get_log(), 200
