"""
Task Tracker REST API — ports routes from my-time-traker/app/api into aw-server.

Endpoints (all prefixed with /api/0/task-tracker/):
  GET    /tasks                           → list all tasks
  POST   /tasks                           → create task
  DELETE /tasks/<task_id>                 → delete task
  POST   /tasks/<task_id>/select          → activate task, close other time entries
  POST   /tasks/<task_id>/deselect        → deactivate task, close open time entries
  GET    /tasks/<task_id>/time-entries    → list time entries for task
  GET    /tasks/<task_id>/app-usages      → list app usages for task
  PUT    /tasks/<task_id>/app-usages      → update app usage category
  GET    /activity-watch?taskId=&start=&end=
                                          → sync ActivityWatch data into AppUsage
  GET    /templates                       → list all templates
  POST   /templates                       → create template
  PATCH  /templates/<template_id>         → update template
  DELETE /templates/<template_id>         → delete template
"""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

from .models import AppUsage, Task, Template, TimeEntry, db_proxy

logger = logging.getLogger(__name__)

bp = Blueprint("task_tracker", __name__, url_prefix="/api/0/task-tracker")


def _to_utc_iso(dt) -> str:
    """Convert a datetime (naive/aware/str, assumed local if naive) to UTC ISO string for AW queries."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        # Treat naive datetime as local time, convert to UTC
        local_dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return local_dt.astimezone(timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


# ── helpers ─────────────────────────────────────────────────────────────

def _json_response(data, status=200):
    return jsonify(data), status


def _error_response(message, status=400):
    return jsonify({"error": message}), status


# ── Tasks ───────────────────────────────────────────────────────────────

@bp.route("/tasks", methods=["GET"])
def get_tasks():
    try:
        tasks = [t.to_dict() for t in Task.select().order_by(Task.created_at.desc())]
        return _json_response(tasks)
    except Exception as e:
        logger.exception("Error fetching tasks")
        return _error_response("Failed to fetch tasks", 500)


@bp.route("/tasks", methods=["POST"])
def create_task():
    try:
        data = request.get_json(force=True)
        name = (data or {}).get("name")
        description = (data or {}).get("description")

        if not name:
            return _error_response("Task name is required", 400)

        task = Task.create(name=name, description=description)
        return _json_response(task.to_dict(), 201)
    except Exception as e:
        logger.exception("Error creating task")
        return _error_response("Failed to create task", 500)


@bp.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    try:
        deleted = Task.delete_by_id(task_id)
        if deleted:
            return _json_response({"success": True})
        return _error_response("Task not found", 404)
    except Exception as e:
        logger.exception("Error deleting task")
        return _error_response("Failed to delete task", 500)


# ── Task selection ──────────────────────────────────────────────────────

@bp.route("/tasks/<int:task_id>/select", methods=["POST"])
def select_task(task_id):
    try:
        task = Task.get_or_none(Task.id == task_id)
        if not task:
            return _error_response("Task not found", 404)

        # Deactivate all tasks
        Task.update(is_active=False).execute()

        # Close any open time entries for other tasks (store in UTC)
        now = datetime.now(timezone.utc)
        TimeEntry.update(end_time=now).where(TimeEntry.end_time.is_null()).execute()

        # Activate this task and create new time entry
        task.is_active = True
        task.save()

        time_entry = TimeEntry.create(task=task, start_time=now)
        return _json_response(time_entry.to_dict(), 201)
    except Exception as e:
        logger.exception("Error selecting task")
        return _error_response("Failed to select task", 500)


@bp.route("/tasks/<int:task_id>/deselect", methods=["POST"])
def deselect_task(task_id):
    try:
        task = Task.get_or_none(Task.id == task_id)
        if not task:
            return _error_response("Task not found", 404)

        task.is_active = False
        task.save()

        # Close open time entries for this task (store in UTC)
        TimeEntry.update(end_time=datetime.now(timezone.utc)).where(
            TimeEntry.task == task,
            TimeEntry.end_time.is_null(),
        ).execute()

        return _json_response({"success": True})
    except Exception as e:
        logger.exception("Error deselecting task")
        return _error_response("Failed to deselect task", 500)


# ── Templates ──────────────────────────────────────────────────────────

@bp.route("/templates", methods=["GET"])
def get_templates():
    try:
        task_id = request.args.get("taskId")
        if task_id:
            task_id = int(task_id)
            # Only return general templates + those scoped to this task
            templates = [
                t.to_dict() for t in Template.select().where(
                    (Template.task == task_id) | (Template.task.is_null())
                ).order_by(Template.created_at.desc())
            ]
        else:
            templates = [
                t.to_dict() for t in Template.select().order_by(Template.created_at.desc())
            ]
        return _json_response(templates)
    except Exception as e:
        logger.exception("Error fetching templates")
        return _error_response("Failed to fetch templates", 500)


@bp.route("/templates", methods=["POST"])
def create_template():
    try:
        data = request.get_json(force=True)
        name = (data or {}).get("name")
        category = (data or {}).get("category", "PRODUCTIVE")
        task_id = (data or {}).get("taskId")  # null for general

        if not name:
            return _error_response("Template name is required", 400)

        if task_id and not Task.get_or_none(Task.id == int(task_id)):
            return _error_response("Task not found", 404)

        template = Template.create(
            name=name,
            category=category,
            task=int(task_id) if task_id else None,
        )
        return _json_response(template.to_dict(), 201)
    except Exception as e:
        logger.exception("Error creating template")
        return _error_response("Failed to create template", 500)


@bp.route("/templates/<int:template_id>", methods=["DELETE"])
def delete_template(template_id):
    try:
        deleted = Template.delete_by_id(template_id)
        if deleted:
            return _json_response({"success": True})
        return _error_response("Template not found", 404)
    except Exception as e:
        logger.exception("Error deleting template")
        return _error_response("Failed to delete template", 500)


@bp.route("/templates/<int:template_id>", methods=["PATCH"])
def update_template(template_id):
    try:
        template = Template.get_or_none(Template.id == template_id)
        if not template:
            return _error_response("Template not found", 404)

        data = request.get_json(force=True) or {}
        if "name" in data and data["name"]:
            template.name = data["name"]
        if "category" in data:
            template.category = data["category"]
        if "taskId" in data:
            new_task_id = data["taskId"]
            if new_task_id and not Task.get_or_none(Task.id == int(new_task_id)):
                return _error_response("Task not found", 404)
            template.task = int(new_task_id) if new_task_id else None
        template.save()

        return _json_response(template.to_dict())
    except Exception as e:
        logger.exception("Error updating template")
        return _error_response("Failed to update template", 500)


# ── Time entries ────────────────────────────────────────────────────────

@bp.route("/tasks/<int:task_id>/time-entries", methods=["GET"])
def get_time_entries(task_id):
    try:
        if not Task.get_or_none(Task.id == task_id):
            return _error_response("Task not found", 404)

        entries = [
            e.to_dict()
            for e in TimeEntry.select()
            .where(TimeEntry.task_id == task_id)
            .order_by(TimeEntry.start_time.desc())
        ]
        return _json_response(entries)
    except Exception as e:
        logger.exception("Error fetching time entries")
        return _error_response("Failed to fetch time entries", 500)


# ── App usages ──────────────────────────────────────────────────────────

@bp.route("/tasks/<int:task_id>/app-usages", methods=["GET"])
def get_app_usages(task_id):
    try:
        if not Task.get_or_none(Task.id == task_id):
            return _error_response("Task not found", 404)

        usages = [
            u.to_dict()
            for u in AppUsage.select()
            .where(AppUsage.task_id == task_id)
            .order_by(AppUsage.total_seconds.desc())
        ]
        return _json_response(usages)
    except Exception as e:
        logger.exception("Error fetching app usages")
        return _error_response("Failed to fetch app usages", 500)


@bp.route("/tasks/<int:task_id>/app-usages", methods=["PUT"])
def update_app_usage(task_id):
    try:
        data = request.get_json(force=True)
        app_usage_id = (data or {}).get("appUsageId")
        category = (data or {}).get("category")

        if not app_usage_id or not category:
            return _error_response("appUsageId and category are required", 400)

        usage = AppUsage.get_or_none(AppUsage.id == int(app_usage_id))
        if not usage:
            return _error_response("App usage not found", 404)

        usage.category = category
        usage.save()
        return _json_response(usage.to_dict())
    except Exception as e:
        logger.exception("Error updating app usage")
        return _error_response("Failed to update app usage", 500)


# ── ActivityWatch sync ─────────────────────────────────────────────────

@bp.route("/activity-watch", methods=["GET"])
def activity_watch_sync():
    """
    Fetches events from ActivityWatch's `currentwindow` bucket for the
    given task's time entries and aggregates them into AppUsage rows.
    """
    try:
        task_id = request.args.get("taskId")
        if not task_id:
            return _error_response("taskId is required", 400)

        task_id = int(task_id)
        task = Task.get_or_none(Task.id == task_id)
        if not task:
            return _error_response("Task not found", 404)

        # Fetch buckets from ActivityWatch to find the currentwindow bucket
        aw_base_url = _get_aw_server_url()
        buckets_url = f"{aw_base_url}/api/0/buckets/"
        try:
            req = Request(buckets_url)
            with urlopen(req, timeout=10) as resp:
                buckets = json.loads(resp.read().decode())
        except Exception as e:
            logger.exception("Failed to fetch buckets from ActivityWatch")
            return _error_response("Failed to fetch buckets from ActivityWatch", 502)

        window_bucket = None
        for bid, bdata in buckets.items():
            if bdata.get("type") == "currentwindow":
                window_bucket = bid
                break

        if not window_bucket:
            return _error_response("No currentwindow bucket found", 404)

        # Fetch templates for this task (both general and task-scoped)
        templates = list(Template.select().where(
            (Template.task == task_id) | (Template.task.is_null())
        ))
        # Sort by name length desc so longer (more specific) templates match first
        templates.sort(key=lambda t: len(t.name), reverse=True)

        # Fetch time entries for this task
        time_entries = list(
            TimeEntry.select()
            .where(TimeEntry.task_id == task_id)
            .order_by(TimeEntry.start_time.desc())
        )

        all_events = []
        for entry in time_entries:
            start = _to_utc_iso(entry.start_time)
            end = _to_utc_iso(entry.end_time) if entry.end_time else datetime.now(timezone.utc).isoformat()
            events_url = (
                f"{aw_base_url}/api/0/buckets/{window_bucket}/events"
                f"?{urlencode({'start': start, 'end': end})}"
            )
            try:
                req = Request(events_url)
                with urlopen(req, timeout=10) as resp:
                    events = json.loads(resp.read().decode())
                    all_events.extend(events)
            except Exception as e:
                logger.warning(f"Error fetching events for time entry {entry.id}: {e}")

        def _resolve_template(app: str, title: str):
            """Check if event matches any template (by substring match in app or title).
            Returns (app_name, display_title, category) — either template-based or raw.
            """
            search_text = f"{app} {title}".lower()
            for tmpl in templates:
                if tmpl.name.lower() in search_text:
                    return (
                        tmpl.name,
                        title,
                        tmpl.category,
                    )
            return (f"{app}-{title}", title, "NEUTRAL")

        # Aggregate app usage
        app_map = {}
        for event in all_events:
            app = event.get("data", {}).get("app", "unknown")
            title = event.get("data", {}).get("title", "")
            duration = event.get("duration", 0) or 0

            resolved_name, resolved_title, category = _resolve_template(app, title)
            logger.debug(f"templates: {resolved_name, resolved_title, category}")

            if resolved_name in app_map:
                app_map[resolved_name]["totalSeconds"] += duration
                # Keep the most recent title
                app_map[resolved_name]["title"] = resolved_title
            else:
                app_map[resolved_name] = {
                    "appName": resolved_name,
                    "title": resolved_title,
                    "totalSeconds": duration,
                    "category": category,
                }

        # Upsert into AppUsage
        app_usages = []
        for _, app_data in app_map.items():
            existing = AppUsage.get_or_none(
                (AppUsage.task_id == task_id) &
                (AppUsage.app_name == app_data["appName"])
            )
            if existing:
                existing.total_seconds = app_data["totalSeconds"]
                existing.title = app_data["title"]
                existing.category = app_data["category"]
                existing.save()
                app_usages.append(existing.to_dict())
            else:
                usage = AppUsage.create(
                    task_id=task_id,
                    app_name=app_data["appName"],
                    title=app_data["title"],
                    total_seconds=app_data["totalSeconds"],
                    category=app_data["category"],
                )
                app_usages.append(usage.to_dict())

        return _json_response(app_usages)

    except Exception as e:
        logger.exception("Error syncing app usages")
        return _error_response("Failed to sync app usages", 500)


def _get_aw_server_url():
    """
    Determine the base URL of the running aw-server.
    In testing mode this is http://127.0.0.1:5666, otherwise http://127.0.0.1:5600.
    """
    # Try to infer from the current request's host
    host = request.host.split(":")[0]
    port = request.host.split(":")[1] if ":" in request.host else "5600"
    return f"http://{host}:{port}"
