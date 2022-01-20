import os
import logging
from typing import List, Dict

from flask import Flask, Blueprint, current_app, send_from_directory
from flask_cors import CORS

import aw_datastore
from aw_datastore import Datastore
from .custom_static import get_custom_static_blueprint

from .log import FlaskLogHandler
from .api import ServerAPI
from . import rest

logger = logging.getLogger(__name__)

app_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(app_folder, "static")

root = Blueprint("root", __name__, url_prefix="/")


class AWFlask(Flask):
    def __init__(self, name, *args, **kwargs):
        Flask.__init__(self, name, *args, **kwargs)

        # Is set on later initialization
        self.api = None  # type: ServerAPI


def create_app(
    host: str, testing=True, storage_method=None, cors_origins=[], custom_static=dict()
) -> AWFlask:
    app = AWFlask("aw-server", static_folder=static_folder, static_url_path="")

    if storage_method is None:
        storage_method = aw_datastore.get_storage_methods()["memory"]

    # Only pretty-print JSON if in testing mode (because of performance)
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = testing

    with app.app_context():
        _config_cors(cors_origins, testing)

    app.json_encoder = rest.CustomJSONEncoder

    app.register_blueprint(root)
    app.register_blueprint(rest.blueprint)
    app.register_blueprint(get_custom_static_blueprint(custom_static))

    db = Datastore(storage_method, testing=testing)
    app.api = ServerAPI(db=db, testing=testing)

    # needed for host-header check
    app.config["HOST"] = host

    return app


@root.route("/")
def static_root():
    return current_app.send_static_file("index.html")


@root.route("/css/<path:path>")
def static_css(path):
    return send_from_directory(static_folder + "/css", path)


@root.route("/js/<path:path>")
def static_js(path):
    return send_from_directory(static_folder + "/js", path)


def _config_cors(cors_origins: List[str], testing: bool):
    if cors_origins:
        logger.warning(
            "Running with additional allowed CORS origins specified through config or CLI argument (could be a security risk): {}".format(
                cors_origins
            )
        )

    if testing:
        # Used for development of aw-webui
        cors_origins.append("http://127.0.0.1:27180/*")

    # TODO: This could probably be more specific
    #       See https://github.com/ActivityWatch/aw-server/pull/43#issuecomment-386888769
    cors_origins.append("moz-extension://*")

    # See: https://flask-cors.readthedocs.org/en/latest/
    CORS(current_app, resources={r"/api/*": {"origins": cors_origins}})


# Only to be called from aw_server.main function!
def _start(
    storage_method,
    host: str,
    port: int,
    testing: bool = False,
    cors_origins: List[str] = [],
    custom_static: Dict[str, str] = dict(),
):
    app = create_app(
        host,
        storage_method=storage_method,
        testing=testing,
        cors_origins=cors_origins,
        custom_static=custom_static,
    )
    try:
        app.run(
            debug=testing,
            host=host,
            port=port,
            request_handler=FlaskLogHandler,
            use_reloader=False,
            threaded=False,
        )
    except OSError as e:
        logger.exception(e)
        raise e
