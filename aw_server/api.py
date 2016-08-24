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

fDuration = api.model('Duration', {
    'value': fields.Float,
    'unit': fields.String,
})

# TODO: Move to aw_core.models, construct from JSONSchema (if reasonably straight-forward)
event = api.model('Event', {
    'timestamp': fields.List(fields.DateTime(required=True)),
    'duration': fields.List(fields.Nested(fDuration)),
    'count': fields.List(fields.Integer()),
    'label': fields.List(fields.String(description='Labels on event'))
})

bucket = api.model('Bucket',{
    'id': fields.String(required=True, description='The buckets unique id'),
    'name': fields.String(required=False, description='The buckets readable and renameable name'),
    'type': fields.String(required=True, description='The buckets event type'),
    'client': fields.String(required=True, description='The name of the watcher client'),
    'hostname': fields.String(required=True, description='The hostname of the client that the bucket belongs to'),
    'created': fields.DateTime(required=True, description='The creation datetime of the bucket'),
})

create_bucket = api.model('CreateBucket',{
    'client': fields.String(required=True),
    'type': fields.String(required=True),
    'hostname': fields.String(required=True),
})

class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type, message):
        super().__init__(message)
        self.type = type


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
            raise BadRequest("BucketAlreadyExists","A bucket with this name already exists, cannot create it")
        app.db.create_bucket(
            bucket_id,
            type=data["type"],
            client=data["client"],
            hostname=data["hostname"],
            created=datetime.now()
        )
        return {}, 200


@api.route("/0/buckets/<string:bucket_id>/events")
class EventResource(Resource):
    """
    Used to get and create events in a particular bucket.
    """

    @api.marshal_list_with(event)
    @api.param("limit", "the maximum number of requests to get")
    def get(self, bucket_id):
        """
        Get events from a bucket
        """
        args = request.args
        limit = int(args["limit"]) if "limit" in args else 100

        logger.debug("Received get request for events in bucket '{}'".format(bucket_id))
        return app.db[bucket_id].get(limit)

    @api.expect(event)
    def post(self, bucket_id):
        """
        Create events for a bucket
        """
        logger.debug("Received post request for event in bucket '{}' and data: {}".format(bucket_id, request.get_json()))
        data = request.get_json()
        if isinstance(data, dict):
            app.db[bucket_id].insert(Event(**data))
        elif isinstance(data, list):
            # TODO: LOL, what? there is a db.insert_many
            for event in data:
                app.db[bucket_id].insert(Event(**event))
        else:
            logger.error("Invalid JSON object")
            raise BadRequest("InvalidJSON", "Invalid JSON object")
        return {}, 200


@api.route("/api/0/buckets/<string:bucket_id>/events/chunk")
class EventChunkResource(Resource):
    """
    Used to get chunked events
    """

    @api.param("start", "Start date of chunk")
    @api.param("end", "End date of chunk")
    def get(self, bucket_id):
        """
        Get events from a bucket
        """
        args = request.args
        if not args["start"]:
            return "Start parameter not specified, cannot chunk", 400
        start = args["start"] if "start" in args else str(datetime.now())
        start = iso8601.parse_date(start)
        end = args["end"] if "end" in args else str(datetime.now() - timedelta(days=1))
        end = iso8601.parse_date(end)

        events = app.db[bucket_id].get()

        eventcount = 0
        chunk = {"label": []}
        for event in events:
            eventdate = iso8601.parse_date(event["timestamp"][0])
            if eventdate >= start and eventdate <= end:
                if "label" not in event:
                    print("Shit")
                for label in event["label"]:
                    if label not in chunk:
                        chunk[label] = {"other_labels":[]}
                    for co_label in event["label"]:
                        if co_label != label and co_label not in chunk[label]["other_labels"]:
                            chunk[label]["other_labels"].append(co_label)
                    if "duration" in event:
                        if "duration" not in chunk[label]:
                            chunk[label]["duration"] = event["duration"][0]
                        else:
                            chunk[label]["duration"]["value"] += event["duration"][0]["value"]

                eventcount += 1

        logger.debug("Received chunk request for bucket '{}' between '{}' and '{}'".format(bucket_id, start, end))
        payload = {
            "eventcount": eventcount,
            "chunks": chunk,
        }
        return payload


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

@api.route("/0/log")
class LogResource(Resource):
    """
    Server log of the current instance in json format
    """

    def get(self):
        """
        Get the server log in json format
        """
        payload = []
        with open(get_log_file_path(), 'r') as log_file:
            for line in log_file.readlines()[::-1]:
                payload.append(json.loads(line))
        return payload, 200
