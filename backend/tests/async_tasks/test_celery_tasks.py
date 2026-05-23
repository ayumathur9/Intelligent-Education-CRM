"""
Tests for Celery task modules — ASYNC-001/002.
All tasks run synchronously via CELERY_TASK_ALWAYS_EAGER.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Users tasks
# ---------------------------------------------------------------------------

class TestSendWelcomeEmailTask:
    @patch("apps.common.email_service.send_welcome_email")
    def test_sends_email_for_existing_user(self, mock_send, admin_user, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.users.tasks import send_welcome_email_task
        send_welcome_email_task(admin_user.pk)
        mock_send.assert_called_once()

    def test_does_not_raise_for_missing_user(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.users.tasks import send_welcome_email_task
        send_welcome_email_task(999999)  # Non-existent user — must not raise.

    @patch("apps.common.email_service.send_welcome_email")
    def test_inactive_user_skipped(self, mock_send, db, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        user = User.objects.create_user(email="inactive@test.com", password="Pass123!!", is_active=False)
        from apps.users.tasks import send_welcome_email_task
        send_welcome_email_task(user.pk)
        mock_send.assert_not_called()


class TestSendPasswordResetEmailTask:
    @patch("apps.common.email_service.send_password_reset_email")
    def test_sends_reset_email(self, mock_send, admin_user, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.users.tasks import send_password_reset_email_task
        send_password_reset_email_task(admin_user.pk, "https://example.com/reset?token=abc")
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "https://example.com/reset?token=abc" in args[1]

    def test_missing_user_does_not_raise(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.users.tasks import send_password_reset_email_task
        send_password_reset_email_task(999999, "https://example.com/reset")


class TestPurgeExpiredTokensTask:
    def test_purge_runs_without_error(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.users.tasks import purge_expired_tokens
        purge_expired_tokens()  # Should not raise even with empty DB.


class TestSendAssignmentEmailTask:
    @patch("apps.common.email_service.send_assignment_email")
    def test_sends_assignment_email(self, mock_send, admin_user, settings, db):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.crm.models import Student
        student = Student.objects.create(
            full_name="Test Student",
            email="s@test.com",
            student_code="STU-TASK-1",
        )
        from apps.users.tasks import send_assignment_email_task
        send_assignment_email_task(admin_user.pk, student.pk, "Counselor")
        mock_send.assert_called_once()

    def test_missing_staff_does_not_raise(self, settings, db):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.crm.models import Student
        student = Student.objects.create(
            full_name="Test Student",
            email="s2@test.com",
            student_code="STU-TASK-2",
        )
        from apps.users.tasks import send_assignment_email_task
        send_assignment_email_task(999999, student.pk, "Counselor")


# ---------------------------------------------------------------------------
# Audit tasks
# ---------------------------------------------------------------------------

class TestAuditTasks:
    def test_archive_old_audit_logs_runs(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.audit.tasks import archive_old_audit_logs
        archive_old_audit_logs()  # Should not raise.

    def test_log_security_event_creates_record(self, admin_user, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.audit.tasks import log_security_event
        from apps.audit.models import ActivityLog
        count_before = ActivityLog.objects.count()
        log_security_event(
            event_type="test_event",
            user_id=admin_user.pk,
            ip_address="1.2.3.4",
            detail="unit test event",
        )
        assert ActivityLog.objects.count() == count_before + 1

    def test_log_security_event_null_user(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.audit.tasks import log_security_event
        # Should not raise with no user.
        log_security_event(
            event_type="anonymous_event",
            user_id=None,
            ip_address="5.6.7.8",
            detail="no user",
        )


# ---------------------------------------------------------------------------
# Files tasks
# ---------------------------------------------------------------------------

class TestFilesTasks:
    def test_async_malware_scan_missing_file(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.files.tasks import async_malware_scan
        # Non-existent file ID — should return not_found, not raise.
        result = async_malware_scan(999999)
        assert result["status"] == "not_found"

    def test_async_malware_scan_no_path(self, settings):
        """async_malware_scan returns no_path for a file with empty path."""
        settings.CELERY_TASK_ALWAYS_EAGER = True
        from apps.files.models import FileObject
        from apps.users.models import User
        admin = User.objects.filter(role="admin").first()
        if admin:
            obj = FileObject.objects.create(
                bucket="local", path="", public_url="", content_type="image/jpeg",
                size_bytes=0, uploaded_by=admin,
            )
            from apps.files.tasks import async_malware_scan
            result = async_malware_scan(obj.pk)
            assert result["status"] == "no_path"
            obj.delete()
