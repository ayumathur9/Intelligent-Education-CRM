# Ensure Celery app is always imported when Django starts so that
# shared_task and @app.task decorators work across all apps.
from .celery import app as celery_app  # noqa: F401

__all__ = ["celery_app"]
