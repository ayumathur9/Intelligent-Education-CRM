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
) -> ActivityLog:
    if instance is not None:
        ct = ContentType.objects.get_for_model(instance.__class__)
        entity = entity or f"{ct.app_label}.{ct.model}"
        entity_id = entity_id or str(getattr(instance, "pk", ""))
    return ActivityLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity=entity or "",
        entity_id=entity_id or "",
        metadata=metadata or {},
    )

