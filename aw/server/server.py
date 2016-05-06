import logging

from flask import Flask
from flask.ext.cors import CORS

from . import datastore
from .datastore import Datastore


app = Flask("aw-server")
CORS(app)   # See: https://flask-cors.readthedocs.org/en/latest/

# The following will be set when started
app.db = None  # type: Datastore


# Only to be called from aw.server.main function!
def _start(port=5600, testing=False, storage_method=datastore.MONGODB):
    # TODO: Restructure so it's called in a more sane way
    app.db = Datastore(storage_method, testing=testing)
    app.run(debug=testing, port=port)

