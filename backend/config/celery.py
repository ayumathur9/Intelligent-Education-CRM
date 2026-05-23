"""
Celery application for Intelligent Education CRM.

Railway-compatible configuration:
  - Broker  : Redis (REDIS_URL env var)
  - Backend : Redis (same URL)
  - Beat    : DatabaseScheduler via django-celery-beat (optional)
  - Worker  : gunicorn-style concurrency controlled by CELERY_WORKER_CONCURRENCY
"""
from __future__ import annotations

import os

from celery import Celery
from celery.utils.log import get_task_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("crm")

# Read all CELERY_* settings from Django settings module.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS.
app.autodiscover_tasks()

logger = get_task_logger(__name__)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Sanity-check task — confirms the worker can receive and execute jobs."""
    logger.info("Request: %r", self.request)
