import json
import logging
from typing import Mapping, List

from flask import Flask, request, make_response
from flask_restful import Resource, Api

import datastore
from datastore import ActivityDatastore


app = Flask("actwa-server")
api = Api(app)

logger = logging.getLogger("actwa-server")

activitydb = ActivityDatastore(datastore.MONGODB)

class ActivityResource(Resource):
    def get(self, activity_type):
        logger.debug("Received get request for activity type {}".format(activity_type))
        return activitydb.get(activity_type)

    def post(self, activity_type):
        logger.debug("Received post request for activity type and data: {}, {}".format(activity_type, request.get_json()))
        activity = request.get_json()
        activitydb.insert(activity_type, activity)
        return activitydb.get(activity_type), 200


api.add_resource(ActivityResource, "/api/0/activity/<string:activity_type>")

def main():
    app.run(debug=True)

