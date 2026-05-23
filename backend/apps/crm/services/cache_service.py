"""
Cache service — INFRA-003 / PERF-002.

Provides cached aggregate helpers for dashboard views and notification counts.
All cache keys use a versioned prefix ("crm:v2:") to allow instant global
invalidation by bumping the version when schema changes are incompatible.

Cache invalidation strategy:
  - Aggregates: short TTL (2 min) — tolerate slight staleness for performance.
  - School list: medium TTL (5 min) — schools change infrequently.
  - Notification counts: short TTL (30 s) — high-frequency reads, acceptable lag.
  - Explicitly invalidated via invalidate_* helpers called from model signals.

Fallback: If Redis is unavailable, Django falls back to LocMemCache
transparently — cache misses just result in fresh DB queries.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Version prefix — bump this to "crm:v3:" when a breaking schema change requires
# flushing all cached values instantly without touching Redis directly.
_V = "crm:v2:"

_KEY_STUDENT_COUNTS = f"{_V}dashboard:student_counts"
_KEY_LEAD_COUNTS    = f"{_V}dashboard:lead_counts"
_KEY_COURSE_COUNT   = f"{_V}dashboard:course_count"
_KEY_SCHOOL_LIST    = f"{_V}schools:active_list"
_KEY_FOLLOWUP_DUE   = f"{_V}dashboard:followups_due"


def _notif_count_key(user_id: int) -> str:
    return f"{_V}notif:unread:{user_id}"


def _analytics_key(period: str) -> str:
    return f"{_V}analytics:{period}"


# ---------------------------------------------------------------------------
# Dashboard aggregate helpers (cached)
# ---------------------------------------------------------------------------

def get_student_counts() -> dict:
    """Return ``{"total": int, "active": int}`` — cached for CACHE_TTL_DASHBOARD seconds."""
    result = cache.get(_KEY_STUDENT_COUNTS)
    if result is None:
        from apps.crm.models import Student
        result = {
            "total": Student.all_objects.count(),
            "active": Student.objects.filter(is_active=True).count(),
        }
        cache.set(_KEY_STUDENT_COUNTS, result, timeout=getattr(settings, "CACHE_TTL_DASHBOARD", 120))
        logger.debug("Cache miss — refreshed student counts: %s", result)
    return result


def get_lead_counts() -> dict:
    """Return ``{"total": int, "pending": int}`` — cached for CACHE_TTL_DASHBOARD seconds."""
    result = cache.get(_KEY_LEAD_COUNTS)
    if result is None:
        from apps.crm.models import Lead
        result = {
            "total": Lead.objects.count(),
            "pending": Lead.objects.filter(status="new").count(),
        }
        cache.set(_KEY_LEAD_COUNTS, result, timeout=getattr(settings, "CACHE_TTL_DASHBOARD", 120))
        logger.debug("Cache miss — refreshed lead counts: %s", result)
    return result


def get_active_course_count() -> int:
    """Return active course count — cached for CACHE_TTL_DASHBOARD seconds."""
    result = cache.get(_KEY_COURSE_COUNT)
    if result is None:
        from apps.crm.models import Course
        result = Course.objects.filter(is_active=True).count()
        cache.set(_KEY_COURSE_COUNT, result, timeout=getattr(settings, "CACHE_TTL_DASHBOARD", 120))
        logger.debug("Cache miss — refreshed course count: %d", result)
    return result


def get_active_schools() -> list:
    """Return active School queryset as a cached list — TTL = CACHE_TTL_SCHOOL_LIST."""
    result = cache.get(_KEY_SCHOOL_LIST)
    if result is None:
        from apps.crm.models import School
        result = list(
            School.objects.filter(is_active=True)
            .prefetch_related("courses")
            .order_by("country", "name")
        )
        cache.set(_KEY_SCHOOL_LIST, result, timeout=getattr(settings, "CACHE_TTL_SCHOOL_LIST", 300))
        logger.debug("Cache miss — refreshed school list: %d schools", len(result))
    return result


def get_followups_due_today() -> int:
    """Return count of follow-ups due today — PERF-002, cached 60 s."""
    result = cache.get(_KEY_FOLLOWUP_DUE)
    if result is None:
        from django.utils import timezone
        from apps.crm.models import FollowUp
        today = timezone.localdate()
        result = FollowUp.objects.filter(
            scheduled_at__date=today,
            status__in=("pending", "rescheduled"),
        ).count()
        cache.set(_KEY_FOLLOWUP_DUE, result, timeout=60)
    return result


# ---------------------------------------------------------------------------
# PERF-002: Notification unread count cache
# ---------------------------------------------------------------------------

def get_unread_notification_count(user_id: int) -> int:
    """Return unread notification count for a user — cached 30 s."""
    key = _notif_count_key(user_id)
    result = cache.get(key)
    if result is None:
        from apps.notifications.models import Notification
        result = Notification.objects.filter(user_id=user_id, read_at__isnull=True).count()
        cache.set(key, result, timeout=30)
    return result


def invalidate_notification_count(user_id: int) -> None:
    """Clear the cached unread count for a user — called on notification read/create."""
    cache.delete(_notif_count_key(user_id))


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

def invalidate_dashboard_cache() -> None:
    """Delete all dashboard aggregate cache entries."""
    cache.delete_many([_KEY_STUDENT_COUNTS, _KEY_LEAD_COUNTS, _KEY_COURSE_COUNT, _KEY_FOLLOWUP_DUE])
    logger.debug("Dashboard cache invalidated")


def invalidate_school_cache() -> None:
    """Delete the school list cache entry."""
    cache.delete(_KEY_SCHOOL_LIST)
    logger.debug("School list cache invalidated")
