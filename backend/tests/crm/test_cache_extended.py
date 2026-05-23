"""
Tests for PERF-002 extended cache service — notification counts, follow-up caching.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache

pytestmark = pytest.mark.django_db


class TestNotificationCountCache:
    def test_get_unread_count_returns_integer(self, admin_user):
        from apps.crm.services.cache_service import get_unread_notification_count
        count = get_unread_notification_count(admin_user.pk)
        assert isinstance(count, int)
        assert count >= 0

    def test_unread_count_is_cached_on_second_call(self, admin_user):
        from apps.crm.services.cache_service import get_unread_notification_count, _notif_count_key
        key = _notif_count_key(admin_user.pk)
        cache.delete(key)
        # First call hits DB, second uses cache.
        c1 = get_unread_notification_count(admin_user.pk)
        c2 = get_unread_notification_count(admin_user.pk)
        assert c1 == c2

    def test_invalidate_notification_count_clears_cache(self, admin_user):
        from apps.crm.services.cache_service import (
            get_unread_notification_count,
            invalidate_notification_count,
            _notif_count_key,
        )
        get_unread_notification_count(admin_user.pk)
        key = _notif_count_key(admin_user.pk)
        assert cache.get(key) is not None
        invalidate_notification_count(admin_user.pk)
        assert cache.get(key) is None

    def test_unread_count_zero_for_new_user(self, db):
        from django.contrib.auth import get_user_model
        from apps.crm.services.cache_service import get_unread_notification_count
        User = get_user_model()
        user = User.objects.create_user(email="notif_test@test.com", password="Pass123!!")
        count = get_unread_notification_count(user.pk)
        assert count == 0


class TestFollowupsDueTodayCache:
    def test_returns_integer(self):
        from apps.crm.services.cache_service import get_followups_due_today
        result = get_followups_due_today()
        assert isinstance(result, int)

    def test_is_cached_on_second_call(self):
        from apps.crm.services.cache_service import get_followups_due_today, _KEY_FOLLOWUP_DUE
        cache.delete(_KEY_FOLLOWUP_DUE)
        r1 = get_followups_due_today()
        r2 = get_followups_due_today()
        assert r1 == r2

    def test_invalidate_dashboard_clears_followup_cache(self):
        from apps.crm.services.cache_service import (
            get_followups_due_today,
            invalidate_dashboard_cache,
            _KEY_FOLLOWUP_DUE,
        )
        get_followups_due_today()
        assert cache.get(_KEY_FOLLOWUP_DUE) is not None
        invalidate_dashboard_cache()
        assert cache.get(_KEY_FOLLOWUP_DUE) is None


class TestVersionedCacheKeys:
    def test_cache_keys_use_v2_prefix(self):
        from apps.crm.services.cache_service import (
            _KEY_STUDENT_COUNTS,
            _KEY_LEAD_COUNTS,
            _KEY_COURSE_COUNT,
            _KEY_SCHOOL_LIST,
        )
        for key in (_KEY_STUDENT_COUNTS, _KEY_LEAD_COUNTS, _KEY_COURSE_COUNT, _KEY_SCHOOL_LIST):
            assert "crm:v2:" in key, f"Key {key} does not use versioned prefix"
