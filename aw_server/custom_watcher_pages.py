import logging

from flask import Blueprint, send_from_directory, jsonify, request, current_app
from iso8601 import iso8601

from aw_core.manager import Manager


def get_bucket_name_from_watcher_name(buckets, watcher_name: str):
    for bucket in buckets:
        if bucket.startswith(watcher_name):
            return bucket

    logging.warning(f"Cannot find bucket for watcher {watcher_name}")
    return None


def get_custom_watcher_blueprint(testing):
    logger = logging.getLogger(__name__)

    custom_watcher_static_directories = dict()

    _manager = Manager(testing=testing, use_parent_parent=True)

    logger.info(f"Searching for watchers with page support...")

    for module in _manager.modules:
        static_dir, name = module.static_directory, module.name

        if name.startswith("aw-watcher"):
            if static_dir is not None:
                logger.info(f" - Found page support for watcher {name}")
                custom_watcher_static_directories[name] = module.static_directory
            else:
                logger.info(f" - No static folder found in {name}")

    custom_watcher_blueprint = Blueprint("custom_watcher", __name__, url_prefix="/watcher")

    @custom_watcher_blueprint.route("api/supported_watchers")
    def custom_watcher_api_supported_pages():
        return jsonify(list(custom_watcher_static_directories.keys()))

    @custom_watcher_blueprint.route("api/get_data", methods=["POST"])
    def custom_watcher_api_get_data():
        start = iso8601.parse_date(request.json["start"])
        end = iso8601.parse_date(request.json["end"])

        buckets = current_app.api.get_buckets().keys()
        custom_page_data = {
            watcher_name: current_app.api.get_events(get_bucket_name_from_watcher_name(buckets, watcher_name),
                                                     start=start, end=end)
            for watcher_name in custom_watcher_static_directories.keys()
        }
        return jsonify(custom_page_data)

    @custom_watcher_blueprint.route("pages/<string:name>/", defaults={'path': 'index.html'})
    @custom_watcher_blueprint.route("pages/<string:name>/<path:path>")
    def custom_watcher_pages(name: str, path: str):
        print(name, path)
        if name in custom_watcher_static_directories:
            return send_from_directory(custom_watcher_static_directories[name], path)
        else:
            return f"Static content: {path} of watcher: {name} not found!", 404

    return custom_watcher_blueprint
