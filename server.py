import json
import logging
from typing import Mapping, List
from datetime import datetime

from flask import Flask, request, make_response
from flask_restful import Resource, Api

import datastore
from datastore import ActivityDatastore


app = Flask("actwa-server")
api = Api(app)
logger = logging.getLogger("actwa-server")


activitydb = ActivityDatastore(datastore.MONGODB)

# TODO: Might be renamed to EventResource
class ActivityResource(Resource):
    """
    Can be used to store and access activity/event objects with a given type.
    """

    # TODO: Set up so that access is done for a given client, not a given activity_type.
    #       By doing this we can also enforce authentication on a client-basis such that a
    #       malicious client cannot access any data other than what it has the rights to.

    def get(self, activity_type):
        logger.debug("Received get request for activity type {}".format(activity_type))
        return activitydb.get(activity_type)

    def post(self, activity_type):
        logger.debug("Received post request for activity type and data: {}, {}".format(activity_type, request.get_json()))
        activity = request.get_json()
        activitydb.insert(activity_type, activity)
        return activitydb.get(activity_type), 200


heartbeats = {}   # type: Mapping[str, datetime]

# TODO: Might be renamed to WatchdogResource
class HeartbeatResource(Resource):
    """
    WIP!

    Used to give clients the ability to signal that they are alive.

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


api.add_resource(ActivityResource, "/api/0/activity/<string:activity_type>")
api.add_resource(HeartbeatResource, "/api/0/heartbeat/<string:client_name>")

def main():
    """Called from __main__.py"""
    app.run(debug=True)

