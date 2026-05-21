"""
Redis caching tests — INFRA-003.
Tests the cache service layer and cache invalidation via signals.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.crm.services.cache_service import (
    get_student_counts,
    get_lead_counts,
    get_active_course_count,
    get_active_schools,
    invalidate_dashboard_cache,
    invalidate_school_cache,
    _KEY_STUDENT_COUNTS,
    _KEY_LEAD_COUNTS,
    _KEY_COURSE_COUNT,
    _KEY_SCHOOL_LIST,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear all cache entries before each test."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


class TestStudentCountCache:
    def test_returns_dict_with_total_and_active(self, db):
        result = get_student_counts()
        assert "total" in result
        assert "active" in result
        assert isinstance(result["total"], int)
        assert isinstance(result["active"], int)

    def test_cache_hit_avoids_db_query(self, db):
        from django.core.cache import cache
        # Pre-populate cache.
        cache.set(_KEY_STUDENT_COUNTS, {"total": 99, "active": 50})
        result = get_student_counts()
        assert result["total"] == 99
        assert result["active"] == 50

    def test_invalidate_clears_cache(self, db):
        from django.core.cache import cache
        cache.set(_KEY_STUDENT_COUNTS, {"total": 99, "active": 50})
        invalidate_dashboard_cache()
        assert cache.get(_KEY_STUDENT_COUNTS) is None


class TestLeadCountCache:
    def test_returns_dict_with_total_and_pending(self, db):
        result = get_lead_counts()
        assert "total" in result
        assert "pending" in result

    def test_cache_hit(self, db):
        from django.core.cache import cache
        cache.set(_KEY_LEAD_COUNTS, {"total": 42, "pending": 10})
        result = get_lead_counts()
        assert result["total"] == 42


class TestCourseCountCache:
    def test_returns_integer(self, db):
        result = get_active_course_count()
        assert isinstance(result, int)

    def test_cache_hit(self, db):
        from django.core.cache import cache
        cache.set(_KEY_COURSE_COUNT, 7)
        result = get_active_course_count()
        assert result == 7


class TestSchoolListCache:
    def test_returns_list(self, db):
        result = get_active_schools()
        assert isinstance(result, list)

    def test_cache_hit_returns_cached_list(self, db):
        from django.core.cache import cache
        mock_schools = ["school_a", "school_b"]
        cache.set(_KEY_SCHOOL_LIST, mock_schools)
        result = get_active_schools()
        assert result == mock_schools

    def test_invalidate_clears_school_cache(self, db):
        from django.core.cache import cache
        cache.set(_KEY_SCHOOL_LIST, ["school_a"])
        invalidate_school_cache()
        assert cache.get(_KEY_SCHOOL_LIST) is None


class TestCacheInvalidationSignals:
    def test_student_save_invalidates_dashboard_cache(self, db, admin_user):
        from django.core.cache import cache
        from apps.crm.models import Student

        cache.set(_KEY_STUDENT_COUNTS, {"total": 99, "active": 50})

        # Create a student — triggers post_save signal → invalidate_dashboard_cache().
        Student.objects.create(
            full_name="Test Student",
            email="test@example.com",
        )
        # Cache should be cleared.
        assert cache.get(_KEY_STUDENT_COUNTS) is None

    def test_school_save_invalidates_school_cache(self, db, admin_user):
        from django.core.cache import cache
        from apps.crm.models import School

        cache.set(_KEY_SCHOOL_LIST, ["cached_school"])

        School.objects.create(
            name="New School",
            country="UK",
            created_by=admin_user,
        )
        assert cache.get(_KEY_SCHOOL_LIST) is None
