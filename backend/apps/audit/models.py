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
            # Respect reverse-proxy headers (Railway / Nginx).
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if x_forwarded_for:
                # Take the first (client) IP — others are proxy IPs.
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")

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
