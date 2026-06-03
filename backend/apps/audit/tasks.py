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
    Writes to the audit log and triggers real-time alerts for critical events.
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

    # Critical events trigger immediate Sentry capture for real-time alerting.
    _CRITICAL_EVENTS = {
        "account_lockout",
        "brute_force_login",
        "impossible_velocity",
        "token_abuse",
    }
    if event_type in _CRITICAL_EVENTS:
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("security_event", event_type)
                scope.set_tag("ip_address", ip_address)
                scope.set_extra("user_id", user_id)
                scope.set_extra("detail", detail)
                scope.set_level("warning")
                sentry_sdk.capture_message(
                    f"Security alert: {event_type} from {ip_address}",
                    level="warning",
                )
        except Exception:
            pass  # Never let alerting failure block the audit log write


@shared_task(
    bind=True,
    name="apps.audit.tasks.prune_login_failures",
    ignore_result=True,
    soft_time_limit=60,
    time_limit=120,
)
def prune_login_failures(self) -> None:
    """
    Daily: prune DB-backed login failure records older than the lockout window.
    Keeps the table small when Redis is unavailable for extended periods.
    """
    from django.conf import settings
    from django.utils import timezone
    from datetime import timedelta
    from apps.audit.models import LoginFailure

    window = int(getattr(settings, "ACCOUNT_LOCKOUT_SECONDS", 900))
    cutoff = timezone.now() - timedelta(seconds=window * 2)  # 2× window for safety
    deleted, _ = LoginFailure.objects.filter(attempted_at__lt=cutoff).delete()
    logger.info("prune_login_failures: deleted %d stale records", deleted)
