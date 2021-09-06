import logging

from flask import Blueprint, send_from_directory, jsonify, request, current_app, escape
from iso8601 import iso8601


def get_bucket_name_from_watcher_name(buckets, watcher_name: str):
    for bucket in buckets:
        if bucket.startswith(watcher_name):
            return bucket

    logging.warning(f"Cannot find bucket for watcher {watcher_name}")
    return None


def get_custom_static_blueprint(custom_static_directories):
    custom_static_blueprint = Blueprint("custom_static", __name__, url_prefix="/watcher")

    @custom_static_blueprint.route("api/get_data", methods=["POST"])
    def custom_static_api_get_data():
        start = iso8601.parse_date(request.json["start"])
        end = iso8601.parse_date(request.json["end"])

        buckets = current_app.api.get_buckets().keys()
        custom_page_data = {
            watcher_name: current_app.api.get_events(get_bucket_name_from_watcher_name(buckets, watcher_name),
                                                     start=start, end=end)
            for watcher_name in custom_static_directories.keys()
        }
        return jsonify(custom_page_data)

    @custom_static_blueprint.route("pages/")
    def custom_static_supported_pages():
        return jsonify(list(custom_static_directories.keys()))

    @custom_static_blueprint.route("pages/<string:name>/", defaults={'path': 'index.html'})
    @custom_static_blueprint.route("pages/<string:name>/<path:path>")
    def custom_static_pages(name: str, path: str):
        if name in custom_static_directories:
            return send_from_directory(custom_static_directories[name], path)
        else:
            return f"Static content: {escape(path)} of watcher: {escape(name)} not found!", 404

    return custom_static_blueprint
