from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType

from .models import ActivityLog


def log_activity(
    *,
    actor,
    action: str,
    instance=None,
    entity: str | None = None,
    entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    request=None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ActivityLog:
    """
    MED-4: Record an activity log entry.

    Pass ``request`` to automatically extract IP and User-Agent, or pass
    ``ip_address`` / ``user_agent`` directly for non-HTTP contexts.
    """
    if instance is not None:
        ct = ContentType.objects.get_for_model(instance.__class__)
        entity = entity or f"{ct.app_label}.{ct.model}"
        entity_id = entity_id or str(getattr(instance, "pk", ""))

    extra: dict[str, Any] = dict(metadata or {})

    if request is not None:
        if not ip_address:
            ip_address = _extract_ip(request)
        if not user_agent:
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]

    if ip_address:
        extra["ip"] = ip_address
    if user_agent:
        extra["ua"] = user_agent

    return ActivityLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity=entity or "",
        entity_id=entity_id or "",
        metadata=extra,
    )


def _extract_ip(request) -> str:
    """Extract the real client IP, respecting trusted proxy headers."""
    try:
        from ipware import get_client_ip
        ip, _ = get_client_ip(request)
        return ip or ""
    except ImportError:
        pass
    # Fallback: trust first entry in X-Forwarded-For (may be spoofed without a proxy).
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


