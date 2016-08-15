from typing import List, Dict
from datetime import datetime, timedelta
import binascii
import os
import json
import iso8601

from flask import request
from flask_restplus import Api, Resource, fields

from aw_core.models import Event
from . import app, logger
from .log import get_log_file_path


# SECURITY
# As we work our way through features, disable (while this is False, we should only accept connections from localhost)
SECURITY_ENABLED = False

# For the planned zeroknowledge storage feature
ZEROKNOWLEDGE_ENABLED = False

api = Api(app)


fDuration = api.model('Duration', {
    'value': fields.Float,
    'unit': fields.String,
})

# TODO: Move to aw_core.models, construct from JSONSchema (if reasonably straight-forward)
event = api.model('Event', {
    'timestamp': fields.List(fields.DateTime(required=True)),
    'duration': fields.List(fields.Nested(fDuration)),
    'label': fields.List(fields.String(description='Labels on event'))
})

bucket = api.model('Bucket', {
    'id': fields.String(required=True, description='The buckets unique identifier'),
    'created': fields.DateTime(required=True),
    'client': fields.String(description='The client in charge of sending data to the bucket'),
    'hostname': fields.String(description='The hostname that the client is running on')
})


@api.route("/api/0/buckets")
class BucketsResource(Resource):
    """
    Used to list buckets.
    """

    @api.marshal_list_with(bucket)
    def get(self):
        """
        Get list of all buckets
        """
        logger.debug("Received get request for buckets")
        return app.db.buckets()

@api.route("/api/0/buckets/<string:bucket_id>")
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

    @api.expect(bucket)
    def post(self, bucket_id):
        """
        Create bucktet
        """
        # TODO: Implement bucket creation
        raise NotImplementedError


@api.route("/api/0/buckets/<string:bucket_id>/events")
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
            for event in data:
                app.db[bucket_id].insert(Event(**event))
        else:
            logger.error("Invalid JSON object")
            return {}, 500
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
                if "duration" in event:
                    if chunk["duration"]:
                        chunk["duration"] = str(iso8601.parse_date(chunk["duration"]) + iso8601.parse_date(event["duration"]))
                    else:
                        chunk["duration"] = event["duration"]
                if "label" in event:
                    chunk["label"].append(event["label"])
                eventcount += 1

        logger.debug("Received chunk request for bucket '{}' between '{}' and '{}'".format(bucket_id, start, end))
        payload = {
            "eventcount": eventcount,
            "chunks": chunk,
        }
        return payload


heartbeats = {}   # type: Dict[str, datetime]


@api.route("/api/0/heartbeat/<string:session_id>")
class HeartbeatResource(Resource):
    """
    WIP!

    Used to give clients the ability to signal on regular intervals something particular which can then be post-processed into events.
    The endpoint could compress a list of events which only differ by their timestamps into a event with a list of the timestamps.

    Should store the last time time the client checked in.
    """

    def get(self, client_name):
        logger.debug("Received heartbeat status request for client '{}'".format(client_name))
        if client_name in heartbeats:
            return heartbeats[client_name].isoformat()
        else:
            return "No heartbeat has been received for this client"

    def post(self, client_name):
        logger.debug("Received heartbeat for client '{}'".format(client_name))
        heartbeats[client_name] = datetime.now()
        return "success", 200


@api.route("/api/0/log")
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
