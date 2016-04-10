import json
from typing import Mapping, List

from flask import Flask, request, make_response
from flask_restful import Resource, Api

from datastore import ActivityDatastore


app = Flask("actwa-server")
api = Api(app)


activitydb = ActivityDatastore("mongodb")

class ActivityResource(Resource):
    def get(self, activity_type):
        return activitydb.get(activity_type)

    def put(self, activity_type):
        activity = json.loads(request.form["data"])
        activitydb.insert(activity_type, activity)
        return activitydb.get(activity_type), 200


api.add_resource(ActivityResource, "/api/0/activity/<string:activity_type>")

if __name__ == '__main__':
    app.run(debug=True)

