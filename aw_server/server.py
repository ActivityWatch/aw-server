import logging
from .log import FlaskLogHandler

from flask import Flask
from flask_cors import CORS

from aw_datastore import Datastore


app = Flask("aw-server")
CORS(app)   # See: https://flask-cors.readthedocs.org/en/latest/

# The following will be set when started
app.db = None  # type: Datastore

# Only to be called from aw_server.main function!
def _start(storage_method, port=5600, testing=False):
    app.db = Datastore(storage_method, testing=testing) 
    app.run(debug=testing, port=port, request_handler=FlaskLogHandler)
