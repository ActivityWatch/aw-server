"""Task Tracker sub-package — auto-registers blueprint and inits DB tables."""

from .models import init_tables
from .routes import bp as task_tracker_bp


def register(app):
    """Register the task tracker blueprint on the Flask app and create tables."""
    init_tables()
    app.register_blueprint(task_tracker_bp)
