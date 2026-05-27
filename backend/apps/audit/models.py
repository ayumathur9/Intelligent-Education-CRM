"""
Audit log model — MED-005.

Enhanced to capture:
- IP address of the request originator
- User-agent (browser/device identification)
- Field-level change tracking (before/after values)

Migration: 0002_activitylog_ip_useragent_changes (nullable fields — safe, reversible)
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ActivityLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    action = models.CharField(max_length=120)
    entity = models.CharField(max_length=120, blank=True)
    entity_id = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # MED-005: security enrichment fields (all nullable for backward compatibility)
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        help_text="IP address of the request that triggered this log entry."
    )
    user_agent = models.CharField(
        max_length=512, blank=True, default="",
        help_text="User-agent string from the request headers."
    )
    changes = models.JSONField(
        default=dict, blank=True,
        help_text='Field-level change tracking: {"field": {"old": X, "new": Y}}',
    )

    class Meta:
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["entity", "entity_id"]),
            models.Index(fields=["actor", "created_at"]),   # INFRA-001: missing index added
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.entity}:{self.entity_id}"

    @classmethod
    def log(
        cls,
        *,
        action: str,
        actor=None,
        entity: str = "",
        entity_id: str = "",
        metadata: dict | None = None,
        request=None,
        changes: dict | None = None,
    ) -> "ActivityLog":
        """
        Convenience factory that extracts request context automatically.

        Usage:
            ActivityLog.log(
                action="student_created",
                actor=request.user,
                entity="Student",
                entity_id=str(student.pk),
                request=request,
                changes={"status": {"old": "new", "new": "active"}},
            )
        """
        ip_address = None
        user_agent = ""

        if request is not None:
            # MED-005: Use django-ipware for trusted proxy-aware IP extraction.
            # This respects IPWARE_META_PRECEDENCE_ORDER and only trusts
            # X-Forwarded-For when the immediate connection comes from a known proxy.
            try:
                from ipware import get_client_ip
                ip_address, _ = get_client_ip(request)
            except ImportError:
                # Fallback if ipware is not installed (should not happen in prod).
                xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
                ip_address = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")

            user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]

        return cls.objects.create(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            changes=changes or {},
        )


class LoginFailure(models.Model):
    """
    SEC-FALLBACK: Database-backed login failure tracker.

    Used as a fallback when Redis is unavailable so that brute-force /
    account-lockout protection remains active even during a Redis outage.
    Rows are cheap (email + timestamp only). Pruned by a nightly Celery task.
    """

    email = models.CharField(max_length=254, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempted_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "attempted_at"]),
        ]

    @classmethod
    def record(cls, email: str, ip: str | None = None) -> int:
        """Record a failure and return the total count in the lockout window."""
        from django.conf import settings as _s
        window_seconds = int(getattr(_s, "ACCOUNT_LOCKOUT_SECONDS", 900))
        cls.objects.create(email=email.lower(), ip_address=ip or None)
        cutoff = timezone.now() - timezone.timedelta(seconds=window_seconds)
        return cls.objects.filter(email=email.lower(), attempted_at__gte=cutoff).count()

    @classmethod
    def is_locked(cls, email: str) -> bool:
        """Return True if the email has exceeded the lockout threshold in the window."""
        from django.conf import settings as _s
        threshold = int(getattr(_s, "ACCOUNT_LOCKOUT_THRESHOLD", 10))
        window_seconds = int(getattr(_s, "ACCOUNT_LOCKOUT_SECONDS", 900))
        cutoff = timezone.now() - timezone.timedelta(seconds=window_seconds)
        count = cls.objects.filter(email=email.lower(), attempted_at__gte=cutoff).count()
        return count >= threshold

    @classmethod
    def clear(cls, email: str) -> None:
        """Remove all failures for this email on successful login."""
        cls.objects.filter(email=email.lower()).delete()
