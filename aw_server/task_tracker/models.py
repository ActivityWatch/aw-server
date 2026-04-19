"""
Task Tracker models — Prisma schema ported to Peewee ORM.
Tables: Task, TimeEntry, AppUsage (+ Category enum)
"""

import peewee as pw
from datetime import datetime


def _ensure_dt(val):
    """Return a datetime object regardless of whether peewee returns str or datetime."""
    if val is None:
        return None
    if isinstance(val, str):
        # Peewee may return a stored string for timezone-aware datetimes
        return datetime.fromisoformat(val)
    return val

# Re-use the same peewee proxy that aw_datastore.storages.peewee uses.
# This way our models share the same SQLite database connection.
from aw_datastore.storages.peewee import _db as db_proxy


class BaseModel(pw.Model):
    """Base model — all task-tracker models inherit from this."""

    class Meta:
        database = db_proxy


class Task(BaseModel):
    id = pw.AutoField()
    name = pw.CharField()
    description = pw.CharField(null=True)
    is_active = pw.BooleanField(default=False)
    created_at = pw.DateTimeField(default=datetime.now)
    updated_at = pw.DateTimeField(default=datetime.now)

    class Meta:
        table_name = "task_tracker_task"
        indexes = ()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "isActive": self.is_active,
            "createdAt": _ensure_dt(self.created_at).isoformat(),
            "updatedAt": _ensure_dt(self.updated_at).isoformat(),
        }


class TimeEntry(BaseModel):
    id = pw.AutoField()
    task = pw.ForeignKeyField(Task, backref="timeEntries", on_delete="CASCADE")
    start_time = pw.DateTimeField(default=datetime.now)
    end_time = pw.DateTimeField(null=True)
    created_at = pw.DateTimeField(default=datetime.now)
    updated_at = pw.DateTimeField(default=datetime.now)

    class Meta:
        table_name = "task_tracker_timeentry"

    def to_dict(self):
        return {
            "id": self.id,
            "taskId": self.task_id,
            "startTime": _ensure_dt(self.start_time).isoformat(),
            "endTime": _ensure_dt(self.end_time).isoformat() if self.end_time else None,
            "createdAt": _ensure_dt(self.created_at).isoformat(),
            "updatedAt": _ensure_dt(self.updated_at).isoformat(),
        }


class AppUsage(BaseModel):
    id = pw.AutoField()
    task = pw.ForeignKeyField(Task, backref="appUsages", on_delete="CASCADE")
    app_name = pw.CharField()
    title = pw.CharField(null=True)
    total_seconds = pw.FloatField(default=0)
    category = pw.CharField(default="NEUTRAL")  # Category enum as string
    created_at = pw.DateTimeField(default=datetime.now)
    updated_at = pw.DateTimeField(default=datetime.now)

    class Meta:
        table_name = "task_tracker_appusage"
        indexes = ((("task_id", "app_name"), True),)  # unique(task_id, app_name)

    def to_dict(self):
        return {
            "id": self.id,
            "taskId": self.task_id,
            "appName": self.app_name,
            "title": self.title,
            "totalSeconds": self.total_seconds,
            "category": self.category,
            "createdAt": _ensure_dt(self.created_at).isoformat(),
            "updatedAt": _ensure_dt(self.updated_at).isoformat(),
        }


class Template(BaseModel):
    """A template for quickly creating a new task with a preset category.
    Can be general (task_id is NULL) or scoped to a specific task.
    """
    id = pw.AutoField()
    name = pw.CharField()
    category = pw.CharField(default="PRODUCTIVE")  # PRODUCTIVE / UNPRODUCTIVE / NEUTRAL
    task = pw.ForeignKeyField(Task, null=True, backref="templates", on_delete="SET NULL")
    created_at = pw.DateTimeField(default=datetime.now)
    updated_at = pw.DateTimeField(default=datetime.now)

    class Meta:
        table_name = "task_tracker_template"
        indexes = ()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "taskId": self.task_id,
            "createdAt": _ensure_dt(self.created_at).isoformat(),
            "updatedAt": _ensure_dt(self.updated_at).isoformat(),
        }


def init_tables():
    """Create tables if they don't exist. Called once at server startup."""
    # db_proxy (_db from aw_datastore.storages.peewee) is already initialized
    # by the time this is called (PeeweeStorage.__init__ runs first).
    if not db_proxy.is_connection_usable():
        db_proxy.connect()
    db_proxy.create_tables([Task, TimeEntry, AppUsage, Template], safe=True)
