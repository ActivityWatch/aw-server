from typing import List, Dict
from datetime import datetime
import binascii
import os

from flask import request
from flask_restful import Resource, Api

from . import app, logger


# SECURITY
# As we work our way through features, disable (while this is False, only accept connections from localhost)
SECURITY_ENABLED = False

# For the planned zeroknowledge storage feature
ZEROKNOWLEDGE_ENABLED = False


api = Api(app)


class SessionManager:
    # TODO: Don't rely on in-memory session storage
    def __init__(self):
        self._sessions = {}

    # SECURITY
    def start_session(self, session_id: str) -> str:
        # Returns a session key to be used in all following requests in session
        session_key = binascii.hexlify(os.urandom(24)).decode("utf8")
        self._sessions[session_id] = {
            "session_key": session_key
        }
        return session_key

    # SECURITY
    # TODO: Implement session closing
    def stop_session(self):
        pass

    # SECURITY
    def verify_session(self, session_id, session_key):
        # session_id is public, session_key is secret
        if SECURITY_ENABLED:
            if session_id not in self._sessions:
                return False

            session = self._sessions[session_id]
            return session["session_key"] == session_key
        else:
            return True


session_manager = SessionManager()


# Use the following for authentication using user roles:
#   http://flask.pocoo.org/snippets/98/

@api.resource("/api/0/session/start/<string:session_id>")
class StartSessionResource(Resource):
    def post(self, session_id):
        data = request.get_json()
        session_key = session_manager.start_session(session_id)
        return {"session_key": session_key}


@api.resource("/api/0/session/stop/<string:session_id>")
class StopSessionResource(Resource):
    def post(self, session_id):
        data = request.get_json()
        pass


# TODO: Might be renamed to EventResource
@api.resource("/api/0/activity/<string:session_id>")
class ActivityResource(Resource):
    """
    Can be used to store and access activity/event objects with a given type.
    """

    # TODO: Set up so that access is done for a given client, not a given activity_type.
    #       By doing this we can also enforce authentication on a client-basis such that a
    #       malicious client cannot access any data other than what it has the rights to.

    def get(self, session_id):
        logger.debug("Received get request for activity type {}".format(session_id))
        return app.db[session_id].get()

    def post(self, session_id):
        logger.debug("Received post request for activity type and data: {}, {}".format(session_id, request.get_json()))
        activity = request.get_json()
        app.db[session_id].insert(activity)
        return app.db[session_id].get(), 200


heartbeats = {}   # type: Dict[str, datetime]


# TODO: Might be renamed to WatchdogResource
@api.resource("/api/0/heartbeat/<string:session_id>")
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
