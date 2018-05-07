import os
import logging
from typing import List

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


def _config_cors(cors_origins: List[str], testing: bool):
    if cors_origins:
        logger.warning('Running with additional allowed CORS origins specified through config or CLI argument (could be a security risk): {}'.format(cors_origins))

    if testing:
        # Used for development of aw-webui
        cors_origins.append("127.0.0.1:27180")

    # TODO: This could probably be more specific
    #       See https://github.com/ActivityWatch/aw-server/pull/43#issuecomment-386888769
    cors_origins.append("moz-extension://*")

    # See: https://flask-cors.readthedocs.org/en/latest/
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})


# Only to be called from aw_server.main function!
def _start(storage_method, host: str, port: int, testing: bool=False, cors_origins: List[str] = []):
    _config_cors(cors_origins, testing)

    # Only pretty-print JSON if in testing mode (because of performance)
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = testing

    db = Datastore(storage_method, testing=testing)
    app.api = ServerAPI(db=db, testing=testing)
    try:
        app.run(debug=testing, host=host, port=port, request_handler=FlaskLogHandler, use_reloader=False)
    except OSError as e:
        logger.error(str(e))
        raise e
