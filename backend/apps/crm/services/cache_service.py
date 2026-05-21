"""
Cache service — INFRA-003.

Provides cached aggregate helpers for dashboard views.
All cache keys are prefixed with "crm:" and scoped to avoid collisions.

Cache invalidation strategy:
  - Aggregates: short TTL (2 min) — tolerate slight staleness for performance.
  - School list: medium TTL (5 min) — schools change infrequently.
  - Explicitly invalidated via invalidate_dashboard_cache() and
    invalidate_school_cache() which are called from model post_save signals.

Fallback: If Redis is unavailable, Django falls back to LocMemCache
transparently — cache misses just result in fresh DB queries.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache key constants
# ---------------------------------------------------------------------------

_KEY_STUDENT_COUNTS = "crm:dashboard:student_counts"
_KEY_LEAD_COUNTS = "crm:dashboard:lead_counts"
_KEY_COURSE_COUNT = "crm:dashboard:course_count"
_KEY_SCHOOL_LIST = "crm:schools:active_list"


# ---------------------------------------------------------------------------
# Dashboard aggregate helpers (cached)
# ---------------------------------------------------------------------------

def get_student_counts() -> dict:
    """
    Return ``{"total": int, "active": int}`` — cached for CACHE_TTL_DASHBOARD seconds.
    """
    result = cache.get(_KEY_STUDENT_COUNTS)
    if result is None:
        from apps.crm.models import Student
        result = {
            "total": Student.all_objects.count(),
            "active": Student.objects.filter(is_active=True).count(),
        }
        ttl = getattr(settings, "CACHE_TTL_DASHBOARD", 120)
        cache.set(_KEY_STUDENT_COUNTS, result, timeout=ttl)
        logger.debug("Cache miss — refreshed student counts: %s", result)
    return result


def get_lead_counts() -> dict:
    """
    Return ``{"total": int, "pending": int}`` — cached for CACHE_TTL_DASHBOARD seconds.
    """
    result = cache.get(_KEY_LEAD_COUNTS)
    if result is None:
        from apps.crm.models import Lead
        result = {
            "total": Lead.objects.count(),
            "pending": Lead.objects.filter(status="new").count(),
        }
        ttl = getattr(settings, "CACHE_TTL_DASHBOARD", 120)
        cache.set(_KEY_LEAD_COUNTS, result, timeout=ttl)
        logger.debug("Cache miss — refreshed lead counts: %s", result)
    return result


def get_active_course_count() -> int:
    """Return active course count — cached for CACHE_TTL_DASHBOARD seconds."""
    result = cache.get(_KEY_COURSE_COUNT)
    if result is None:
        from apps.crm.models import Course
        result = Course.objects.filter(is_active=True).count()
        ttl = getattr(settings, "CACHE_TTL_DASHBOARD", 120)
        cache.set(_KEY_COURSE_COUNT, result, timeout=ttl)
        logger.debug("Cache miss — refreshed course count: %d", result)
    return result


def get_active_schools() -> list:
    """
    Return active School queryset as a cached list — TTL = CACHE_TTL_SCHOOL_LIST.
    Returns a freshly-evaluated queryset list (not a live queryset).
    """
    result = cache.get(_KEY_SCHOOL_LIST)
    if result is None:
        from apps.crm.models import School
        result = list(
            School.objects.filter(is_active=True)
            .prefetch_related("courses")
            .order_by("country", "name")
        )
        ttl = getattr(settings, "CACHE_TTL_SCHOOL_LIST", 300)
        cache.set(_KEY_SCHOOL_LIST, result, timeout=ttl)
        logger.debug("Cache miss — refreshed school list: %d schools", len(result))
    return result


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

def invalidate_dashboard_cache() -> None:
    """Delete all dashboard aggregate cache entries."""
    cache.delete_many([_KEY_STUDENT_COUNTS, _KEY_LEAD_COUNTS, _KEY_COURSE_COUNT])
    logger.debug("Dashboard cache invalidated")


def invalidate_school_cache() -> None:
    """Delete the school list cache entry."""
    cache.delete(_KEY_SCHOOL_LIST)
    logger.debug("School list cache invalidated")
