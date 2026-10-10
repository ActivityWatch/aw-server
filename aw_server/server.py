import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aw_datastore
import flask.json.provider
from aw_datastore import Datastore
from aw_datastore.storages.peewee import PeeweeStorage
from flask import (
    Blueprint,
    Flask,
    current_app,
    send_from_directory,
)
from flask_cors import CORS

from . import auth, extension_cors, rest
from .api import ServerAPI
from .custom_static import get_custom_static_blueprint
from .log import FlaskLogHandler

logger = logging.getLogger(__name__)

app_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(app_folder, "static")

root = Blueprint("root", __name__, url_prefix="/")


class AWFlask(Flask):
    def __init__(
        self,
        host: str,
        testing: bool,
        storage_method=None,
        cors_origins=None,
        custom_static=None,
        static_folder=static_folder,
        static_url_path="",
        query_cache: bool = True,
        api_key: str = "",
    ):
        if cors_origins is None:
            cors_origins = []
        if custom_static is None:
            custom_static = {}
        name = "aw-server"
        self.json_provider_class = CustomJSONProvider
        # only prettyprint JSON if testing (due to perf)
        self.json_provider_class.compact = not testing

        # Initialize Flask
        Flask.__init__(
            self,
            name,
            static_folder=static_folder,
            static_url_path=static_url_path,
        )
        self.config["HOST"] = host  # needed for host-header check
        with self.app_context():
            _config_cors(cors_origins, testing)
            auth.register(self, api_key or None)

        # Initialize datastore and API
        if storage_method is None:
            storage_method = aw_datastore.get_storage_methods()["memory"]
        db = Datastore(storage_method, testing=testing)
        if isinstance(db.storage_strategy, PeeweeStorage):
            database = db.storage_strategy.db
            # aw-core enables WAL for concurrent readers and writers. Close
            # its initialization connection before serving request threads.
            database.close()

            @self.teardown_request
            def close_database(error):
                # Peewee opens connections lazily and keeps them thread-local.
                # Release cursors/locks even if handling a request failed.
                if not database.is_closed():
                    database.close()

        self.api = ServerAPI(db=db, testing=testing, query_cache=query_cache)

        self.register_blueprint(root)
        self.register_blueprint(rest.blueprint)
        self.register_blueprint(get_custom_static_blueprint(custom_static))


class CustomJSONProvider(flask.json.provider.DefaultJSONProvider):
    # encoding/decoding of datetime as iso8601 strings
    # encoding of timedelta as second floats
    def default(self, obj, *args, **kwargs):
        try:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, timedelta):
                return obj.total_seconds()
        except TypeError:
            pass
        return super().default(obj)


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
            "Running with additional allowed CORS origins specified through config "
            "or CLI argument (could be a security risk): {}".format(cors_origins)
        )

    if testing:
        # Used for development of aw-webui
        cors_origins.append("http://127.0.0.1:27180/*")

    # Capture user-configured origins before appending the built-in wildcard.
    # extension_cors uses this list to exempt explicit opt-ins from scope narrowing.
    user_origins = list(cors_origins)

    # TODO: This could probably be more specific
    #       See https://github.com/ActivityWatch/aw-server/pull/43#issuecomment-386888769
    cors_origins.append("moz-extension://*")

    # See: https://flask-cors.readthedocs.org/en/latest/
    CORS(current_app, resources={r"/api/*": {"origins": cors_origins}})

    # Narrow the moz-extension wildcard to only the endpoints aw-watcher-web needs.
    # See aw_server/extension_cors.py and ActivityWatch/aw-server-rust#637.
    extension_cors.register(current_app._get_current_object(), user_origins)


# Only to be called from aw_server.main function!
def _start(
    storage_method,
    host: str,
    port: int,
    testing: bool = False,
    cors_origins: Optional[List[str]] = None,
    custom_static: Optional[Dict[str, str]] = None,
    query_cache: bool = True,
    api_key: str = "",
):
    app = AWFlask(
        host,
        testing=testing,
        storage_method=storage_method,
        cors_origins=cors_origins,
        custom_static=custom_static,
        query_cache=query_cache,
        api_key=api_key,
    )
    try:
        app.run(
            debug=testing,
            host=host,
            port=port,
            request_handler=FlaskLogHandler,
            use_reloader=False,
            threaded=True,
        )
    except OSError as e:
        logger.exception(e)
        raise e
