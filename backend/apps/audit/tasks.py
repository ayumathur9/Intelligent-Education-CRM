"""Celery tasks for the audit app — ASYNC-002."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.audit.tasks.archive_old_audit_logs",
    ignore_result=True,
    soft_time_limit=120,
    time_limit=240,
)
def archive_old_audit_logs(self) -> None:
    """
    Daily at 00:30: delete audit entries older than 90 days.
    Audit logs older than 90 days have low investigative value and
    consuming unbounded DB space is an operational risk.
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.audit.models import ActivityLog

    cutoff = timezone.now() - timedelta(days=90)
    deleted_count, _ = ActivityLog.objects.filter(created_at__lt=cutoff).delete()
    logger.info("archive_old_audit_logs: deleted %d entries older than 90 days", deleted_count)


@shared_task(
    bind=True,
    name="apps.audit.tasks.log_security_event",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 15},
)
def log_security_event(self, event_type: str, user_id: int | None, ip_address: str, detail: str) -> None:
    """
    Async security event logging — OBS-003.
    Writes to the audit log without blocking the request/response cycle.
    """
    from apps.audit.models import ActivityLog

    ActivityLog.objects.create(
        action=event_type,
        actor_id=user_id,
        ip_address=ip_address,
        metadata={"detail": detail},
    )
    logger.info(
        "security_event type=%s user=%s ip=%s",
        event_type,
        user_id,
        ip_address,
    )
