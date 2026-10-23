import json
import re
import traceback
from functools import wraps
from threading import Lock
from typing import Callable, Dict, Optional, TypeVar
from urllib.parse import urlsplit

import iso8601
from aw_core import schema
from aw_core.models import Event
from aw_query.exceptions import QueryException
from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    make_response,
    request,
    stream_with_context,
)
from flask_restx import Api, Resource, fields
from werkzeug.exceptions import RequestEntityTooLarge

from . import logger
from .api import ImportRollbackError, ServerAPI
from .csv_export import content_disposition
from .exceptions import BadRequest, Unauthorized

T = TypeVar("T")


def host_header_check(f):
    """
    Protects against DNS rebinding attacks (see https://github.com/ActivityWatch/activitywatch/security/advisories/GHSA-v9fg-6g9j-h4x4)

    Some discussion in Syncthing how they do it: https://github.com/syncthing/syncthing/issues/4819
    """

    @wraps(f)
    def decorator(*args, **kwargs):
        server_host = current_app.config["HOST"]
        req_host = request.headers.get("host", None)
        if server_host == "0.0.0.0":
            logger.warning(
                "Server is listening on 0.0.0.0, host header check is disabled (potential security issue)."
            )
        elif req_host is None:
            return {"message": "host header is missing"}, 400
        else:
            try:
                # Host is an authority: IPv6 literals use brackets, optionally
                # followed by a port. Splitting on ':' truncates them to '['.
                authority = urlsplit("//" + req_host)
                # urlsplit accepts empty ports and discards empty query or
                # fragment delimiters. Require a complete Host authority too.
                valid = (
                    re.fullmatch(
                        r"(?:\[[^\[\]\s/?#@]+\]|[^\s:/?#@\[\]]+)(?::[0-9]+)?",
                        req_host,
                    )
                    is not None
                    and authority.hostname
                    in ["localhost", "127.0.0.1", "::1", server_host.lower()]
                    and authority.username is None
                    and authority.password is None
                    and not authority.path
                    and not authority.query
                    and not authority.fragment
                )
                # Validate the optional port too (including unbracketed IPv6).
                authority.port
            except ValueError:
                valid = False
            if not valid:
                return {"message": f"host header is invalid (was {req_host})"}, 400
        return f(*args, **kwargs)

    return decorator


blueprint = Blueprint("api", __name__, url_prefix="/api")
api = Api(blueprint, doc="/", decorators=[host_header_check])


# Loads event and bucket schema from JSONSchema in aw_core
event = api.schema_model("Event", schema.get_json_schema("event"))
bucket = api.schema_model("Bucket", schema.get_json_schema("bucket"))
buckets_export = api.schema_model("Export", schema.get_json_schema("export"))

# TODO: Construct all the models from JSONSchema?
#       A downside to contructing from JSONSchema: flask-restplus does not have marshalling support

info = api.model(
    "Info",
    {
        "hostname": fields.String(),
        "version": fields.String(),
        "testing": fields.Boolean(),
        "device_id": fields.String(),
        "profile": fields.String(),
    },
)

device = api.model(
    "Device",
    {
        "id": fields.String(description="Stable device identifier (UUID)"),
        "hostname": fields.String(description="Current hostname of the device"),
    },
)

create_bucket = api.model(
    "CreateBucket",
    {
        "client": fields.String(required=True),
        "type": fields.String(required=True),
        "hostname": fields.String(required=True),
        "created": fields.String(required=False),
        "data": fields.Raw(required=False),
    },
)

update_bucket = api.model(
    "UpdateBucket",
    {
        "client": fields.String(required=False),
        "type": fields.String(required=False),
        "hostname": fields.String(required=False),
        "data": fields.String(required=False),
    },
)

query = api.model(
    "Query",
    {
        "timeperiods": fields.List(
            fields.String, required=True, description="List of periods to query"
        ),
        "query": fields.List(
            fields.String, required=True, description="String list of query statements"
        ),
        "cache": fields.Boolean(
            required=False,
            description="Set to false to bypass the cache for finished past periods",
        ),
    },
)


def _parse_arg(args, name: str, parse: Callable[[str], T]) -> Optional[T]:
    """Parse an optional query parameter, raising BadRequest on malformed input."""
    if name not in args:
        return None
    try:
        return parse(args[name])
    except ValueError as e:
        raise BadRequest("InvalidParameter", f"Invalid value for parameter {name}: {e}")


def _parse_event(data) -> Event:
    """Construct an Event from client JSON, raising BadRequest on malformed input."""
    if not isinstance(data, dict):
        raise BadRequest("InvalidEvent", "Event must be a JSON object")
    try:
        return Event(**data)
    except (ValueError, TypeError) as e:
        raise BadRequest("InvalidEvent", f"Invalid event: {e}")


def copy_doc(api_method):
    """Decorator that copies another functions docstring to the decorated function.
    Used to copy the docstrings in ServerAPI over to the flask-restplus Resources.
    (The copied docstrings are then used by flask-restplus/swagger)"""

    def decorator(f):
        f.__doc__ = api_method.__doc__
        return f

    return decorator


def request_api() -> ServerAPI:
    return getattr(g, "device_api", current_app.api)


class DeviceResource(Resource):
    """Reuse legacy validation/auth/streaming with a request-local API view."""

    def dispatch_request(self, *args, **kwargs):
        device_id = kwargs.pop("device_id", None)
        if device_id is not None:
            try:
                g.device_api = request_api().for_device(device_id)
            except NotImplementedError as e:
                return {"message": str(e)}, 501
        return super().dispatch_request(*args, **kwargs)


@api.errorhandler(ValueError)
def storage_value_error(error):
    status = 409 if str(error).startswith("Ambiguous bucket") else 400
    return {"message": str(error)}, status


# SERVER INFO


@api.route("/0/info")
class InfoResource(Resource):
    @api.marshal_with(info)
    @copy_doc(ServerAPI.get_info)
    def get(self) -> Dict[str, Dict]:
        return request_api().get_info()


@api.route("/0/devices")
class DevicesResource(Resource):
    @api.marshal_list_with(device)
    @copy_doc(ServerAPI.get_devices)
    def get(self):
        return request_api().get_devices()


@api.route("/0/devices/buckets")
class DeviceBucketsResource(Resource):
    def get(self):
        return current_app.api.device_buckets()


@api.route("/0/devices/export")
class DevicesExportResource(Resource):
    def get(self):
        return jsonify(current_app.api.device_buckets(export=True))


@api.route("/0/devices/import")
class DevicesImportResource(Resource):
    def post(self):
        try:
            current_app.api.import_devices(request.get_json())
        except NotImplementedError as e:
            return {"message": str(e)}, 501
        except ImportRollbackError as e:
            logger.error(f"Device import failed with incomplete rollback: {e!r}")
            return {"message": str(e)}, 500
        except (ValueError, TypeError, KeyError) as e:
            return {"message": str(e)}, 400
        return {"message": "Import successful"}, 200


# BUCKETS


@api.route("/0/buckets/", "/0/devices/<string:device_id>/buckets/")
class BucketsResource(DeviceResource):
    # TODO: Add response marshalling/validation
    @copy_doc(ServerAPI.get_buckets)
    def get(self) -> Dict[str, Dict]:
        return request_api().get_buckets()


@api.route(
    "/0/buckets/<string:bucket_id>",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>",
)
class BucketResource(DeviceResource):
    @api.doc(model=bucket)
    @copy_doc(ServerAPI.get_bucket_metadata)
    def get(self, bucket_id):
        return request_api().get_bucket_metadata(bucket_id)

    @api.expect(create_bucket)
    @copy_doc(ServerAPI.create_bucket)
    def post(self, bucket_id):
        data = request.get_json()
        if not isinstance(data, dict):
            raise BadRequest("InvalidBucket", "Bucket must be a JSON object")
        missing = [k for k in ("type", "client", "hostname") if k not in data]
        if missing:
            raise BadRequest(
                "MissingParameter",
                f"Missing required field(s): {', '.join(missing)}",
            )
        # Optional, like aw-server-rust: aw-sync sets created and data
        # ($aw.sync.origin) on the buckets it pulls.
        bucket_data = data.get("data")
        if bucket_data is not None and not isinstance(bucket_data, dict):
            raise BadRequest("InvalidData", "Bucket data must be an object")
        try:
            created = (
                iso8601.parse_date(data["created"])
                if data.get("created") is not None
                else None
            )
        except iso8601.ParseError as e:
            raise BadRequest("InvalidCreated", str(e))
        bucket_created = request_api().create_bucket(
            bucket_id,
            event_type=data["type"],
            client=data["client"],
            hostname=data["hostname"],
            created=created,
            data=bucket_data,
        )
        if bucket_created:
            return {}, 200
        else:
            return {}, 304

    @api.expect(update_bucket)
    @copy_doc(ServerAPI.update_bucket)
    def put(self, bucket_id):
        data = request.get_json()
        request_api().update_bucket(
            bucket_id,
            event_type=data.get("type"),
            client=data.get("client"),
            hostname=data.get("hostname"),
            data=data.get("data"),
        )
        return {}, 200

    @copy_doc(ServerAPI.delete_bucket)
    @api.param("force", "Needs to be =1 to delete a bucket it non-testing mode")
    def delete(self, bucket_id):
        args = request.args
        if not request_api().testing:
            if "force" not in args or args["force"] != "1":
                msg = "Deleting buckets is only permitted if aw-server is running in testing mode or if ?force=1"
                raise Unauthorized("DeleteBucketUnauthorized", msg)

        request_api().delete_bucket(bucket_id)
        return {}, 200


# EVENTS


@api.route(
    "/0/buckets/<string:bucket_id>/events",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/events",
)
class EventsResource(DeviceResource):
    # For some reason this doesn't work with the JSONSchema variant
    # Marshalling doesn't work with JSONSchema events
    # @api.marshal_list_with(event)
    @api.doc(model=event)
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    @copy_doc(ServerAPI.get_events)
    def get(self, bucket_id):
        args = request.args
        limit = _parse_arg(args, "limit", int)
        if limit is None:
            limit = -1
        start = _parse_arg(args, "start", iso8601.parse_date)
        end = _parse_arg(args, "end", iso8601.parse_date)

        events = request_api().get_events(bucket_id, limit=limit, start=start, end=end)
        return events, 200

    # TODO: How to tell expect that it could be a list of events? Until then we can't use validate.
    @api.expect(event)
    @copy_doc(ServerAPI.create_events)
    def post(self, bucket_id):
        data = request.get_json()
        logger.debug(
            "Received post request for event in bucket '{}' and data: {}".format(
                bucket_id, data
            )
        )

        if isinstance(data, dict):
            events = [_parse_event(data)]
        elif isinstance(data, list):
            events = [_parse_event(e) for e in data]
        else:
            raise BadRequest("Invalid POST data", "")

        events = request_api().create_events(bucket_id, events)
        return [e.to_json_dict() for e in events], 200


@api.route(
    "/0/buckets/<string:bucket_id>/events/count",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/events/count",
)
class EventCountResource(DeviceResource):
    @api.doc(model=fields.Integer)
    @api.param("start", "Start date of eventcount")
    @api.param("end", "End date of eventcount")
    @copy_doc(ServerAPI.get_eventcount)
    def get(self, bucket_id):
        args = request.args
        start = _parse_arg(args, "start", iso8601.parse_date)
        end = _parse_arg(args, "end", iso8601.parse_date)

        events = request_api().get_eventcount(bucket_id, start=start, end=end)
        return events, 200


# Each id is one datastore round-trip under the write lock, so an unbounded
# list would let one request stall all event writes. Matches aw-server-rust.
MAX_BULK_DELETE_IDS = 10_000


@api.route(
    "/0/buckets/<string:bucket_id>/events/delete",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/events/delete",
)
class EventsDeleteResource(DeviceResource):
    @copy_doc(ServerAPI.delete_events)
    def post(self, bucket_id: str):
        data = request.get_json(silent=True)
        ids = data.get("ids") if isinstance(data, dict) else None
        if not isinstance(ids, list) or not all(
            isinstance(i, int)
            and not isinstance(i, bool)
            and 0 <= i <= 9223372036854775807  # non-negative, within SQLite int64 range
            for i in ids
        ):
            raise BadRequest(
                "InvalidBody", 'Body must be {"ids": [...]} with integer ids'
            )
        if len(ids) > MAX_BULK_DELETE_IDS:
            raise RequestEntityTooLarge(
                f"Too many ids in bulk delete request: {len(ids)} "
                f"(max {MAX_BULK_DELETE_IDS})"
            )
        return request_api().delete_events(bucket_id, ids), 200


@api.route(
    "/0/buckets/<string:bucket_id>/events/<int:event_id>",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/events/<int:event_id>",
)
class EventResource(DeviceResource):
    @api.doc(model=event)
    @copy_doc(ServerAPI.get_event)
    def get(self, bucket_id: str, event_id: int):
        logger.debug(
            f"Received get request for event with id '{event_id}' in bucket '{bucket_id}'"
        )
        event = request_api().get_event(bucket_id, event_id)
        if event:
            return event, 200
        else:
            return None, 404

    @copy_doc(ServerAPI.delete_event)
    def delete(self, bucket_id: str, event_id: int):
        logger.debug(
            "Received delete request for event with id '{}' in bucket '{}'".format(
                event_id, bucket_id
            )
        )
        success = request_api().delete_event(bucket_id, event_id)
        return {"success": success}, 200


@api.route(
    "/0/buckets/<string:bucket_id>/heartbeat",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/heartbeat",
)
class HeartbeatResource(DeviceResource):
    # Class-level lock shared across all instances.
    # Flask-RESTX creates a new Resource instance per request, so an
    # instance-level lock would provide no mutual exclusion.
    lock = Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @api.expect(event, validate=True)
    @api.param(
        "pulsetime", "Largest timewindow allowed between heartbeats for them to merge"
    )
    @copy_doc(ServerAPI.heartbeat)
    def post(self, bucket_id):
        heartbeat = _parse_event(request.get_json())

        pulsetime = _parse_arg(request.args, "pulsetime", float)
        if pulsetime is None:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        # This lock is meant to ensure that only one heartbeat is processed at a time,
        # as the heartbeat function is not thread-safe.
        # This should maybe be moved into the api.py file instead (but would be very messy).
        acquired = self.lock.acquire(timeout=10)
        if not acquired:
            logger.warning(
                "Heartbeat lock could not be acquired within timeout, rejecting request."
            )
            return {"message": "Server busy, try again later"}, 503
        try:
            event = request_api().heartbeat(bucket_id, heartbeat, pulsetime)
        finally:
            self.lock.release()
        return event.to_json_dict(), 200


# QUERY


@api.route("/0/query/", "/0/devices/<string:device_id>/query")
class QueryResource(DeviceResource):
    # TODO Docs
    @api.expect(query, validate=True)
    @api.param("name", "Name of the query")
    @api.param(
        "cache",
        "Set to false to bypass the server-side cache of results for finished past periods"
        " (also accepted as a boolean `cache` field in the body). Default: true.",
    )
    def post(self):
        name = ""
        if "name" in request.args:
            name = request.args["name"]
        query = request.get_json()
        cache = request.args.get("cache", "true").lower() not in ("false", "0", "no")
        if query.get("cache") is False:
            cache = False
        try:
            result = request_api().query2(
                name, query["query"], query["timeperiods"], cache
            )
            return jsonify(result)
        except QueryException as qe:
            traceback.print_exc()
            return {"type": type(qe).__name__, "message": str(qe)}, 400


# EXPORT AND IMPORT


@api.route("/0/export", "/0/devices/<string:device_id>/export")
class ExportAllResource(DeviceResource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_all)
    def get(self):
        buckets_export = request_api().export_all()
        payload = {"buckets": buckets_export}
        response = make_response(json.dumps(payload))
        response.mimetype = "application/json"
        filename = "aw-buckets-export.json"
        response.headers["Content-Disposition"] = "attachment; filename={}".format(
            filename
        )
        return response


# TODO: Perhaps we don't need this, could be done with a query argument to /0/export instead
@api.route(
    "/0/buckets/<string:bucket_id>/export",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/export",
)
class BucketExportResource(DeviceResource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_bucket)
    def get(self, bucket_id):
        bucket_export = request_api().export_bucket(bucket_id)
        payload = {"buckets": {bucket_export["id"]: bucket_export}}
        response = make_response(json.dumps(payload))
        response.mimetype = "application/json"
        filename = "aw-bucket-export_{}.json".format(bucket_export["id"])
        response.headers["Content-Disposition"] = "attachment; filename={}".format(
            filename
        )
        return response


@api.route(
    "/0/buckets/<string:bucket_id>/export/csv",
    "/0/devices/<string:device_id>/buckets/<string:bucket_id>/export/csv",
)
class BucketExportCsvResource(DeviceResource):
    @api.param("limit", "the maximum number of events to export")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    @copy_doc(ServerAPI.export_bucket_csv)
    def get(self, bucket_id):
        args = request.args
        try:
            limit = int(args["limit"]) if "limit" in args else -1
            start = iso8601.parse_date(args["start"]) if "start" in args else None
            end = iso8601.parse_date(args["end"]) if "end" in args else None
        except (ValueError, iso8601.ParseError) as e:
            raise BadRequest("InvalidParameter", str(e))
        rows = request_api().export_bucket_csv(
            bucket_id, limit=limit, start=start, end=end
        )
        response = Response(stream_with_context(rows), mimetype="text/csv")
        response.headers["Content-Disposition"] = content_disposition(
            f"aw-events-export-{bucket_id}.csv"
        )
        return response


@api.route("/0/import")
class ImportAllResource(Resource):
    @api.expect(buckets_export)
    @copy_doc(ServerAPI.import_all)
    def post(self):
        try:
            # If import comes from a form in the web-ui
            if len(request.files) > 0:
                # web-ui form only allows one file, but technically it's possible to
                # upload multiple files at the same time
                # Import every file as one batch, so a failure rolls back all of them.
                buckets = {}
                for filename, f in request.files.items():
                    file_buckets = json.loads(f.stream.read())["buckets"]
                    if not isinstance(file_buckets, dict):
                        raise ValueError(
                            "'buckets' must be an object mapping bucket IDs to buckets"
                        )
                    for key, bucket in file_buckets.items():
                        if key in buckets:
                            raise ValueError(
                                f"Bucket '{key}' appears in more than one uploaded file."
                            )
                        buckets[key] = bucket
                request_api().import_all(buckets)
            # Normal import from body
            else:
                buckets = request.get_json()["buckets"]
                request_api().import_all(buckets)
        except ImportRollbackError as e:
            # The import failed *and* rollback could not remove some created
            # buckets: they are still stored, so a retry would be rejected as a
            # duplicate. This is a server-side failure, but the message names the
            # buckets to clean up before retrying.
            logger.error(f"Import failed with incomplete rollback: {e!r}")
            return {"message": str(e)}, 500
        except (KeyError, TypeError, ValueError) as e:
            # Malformed export or a bucket that already exists: the client's
            # fault, so a 400 with a message instead of a traceback.
            logger.warning(f"Import failed: {e!r}")
            reason = f"missing field {e}" if isinstance(e, KeyError) else str(e)
            return {"message": f"Import failed: {reason}"}, 400
        return {"message": "Import successful"}, 200


# LOGGING


@api.route("/0/log")
class LogResource(Resource):
    @copy_doc(ServerAPI.get_log)
    def get(self):
        return request_api().get_log(), 200


# SETTINGS


@api.route("/0/settings", defaults={"key": ""})
@api.route("/0/settings/<string:key>")
class SettingsResource(Resource):
    def get(self, key: str):
        data = request_api().get_setting(key)
        return jsonify(data)

    def post(self, key: str):
        if not key:
            raise BadRequest("MissingParameter", "Missing required parameter key")
        data = request_api().set_setting(key, request.get_json())
        return data
