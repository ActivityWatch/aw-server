import os
import logging

from flask import Flask, send_from_directory
from flask_cors import CORS

from aw_datastore import Datastore

from .log import FlaskLogHandler
from .api import ServerAPI


logger = logging.getLogger(__name__)

app_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(app_folder, 'static')


class AWFlask(Flask):
    def __init__(self, name, *args, **kwargs):
        Flask.__init__(self, name, *args, **kwargs)

        # Is set on later initialization
        self.api = None  # type: ServerAPI


app = AWFlask("aw-server", static_folder=static_folder, static_url_path='')


@app.route("/")
def static_root():
    return app.send_static_file('index.html')
    return send_from_directory('/', 'index.html')


@app.route("/css/<path:path>")
def static_css(path):
    return send_from_directory(static_folder + '/css', path)


@app.route("/js/<path:path>")
def static_js(path):
    return send_from_directory(static_folder + '/js', path)


# Only to be called from aw_server.main function!
def _start(storage_method, host, port, testing=False):
    origins = "moz-extension://*"
    if testing:
        # CORS won't be supported in non-testing mode until we fix our authentication
        logger.warning("CORS is enabled when ran in testing mode, don't store any sensitive data when running in testing mode!")
        origins = "*"
    # See: https://flask-cors.readthedocs.org/en/latest/
    CORS(app, resources={r"/api/*": {"origins": origins}})

    db = Datastore(storage_method, testing=testing)
    app.api = ServerAPI(db=db, testing=testing)
    app.run(debug=testing, host=host, port=port, request_handler=FlaskLogHandler, use_reloader=False)
