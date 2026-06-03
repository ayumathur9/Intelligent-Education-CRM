"""
Celery tasks for asynchronous email delivery.

All tasks:
- Run on the dedicated "email" queue (see CELERY_TASK_ROUTES in settings.py).
- Auto-retry on transient SMTP failures only (see email_service._TRANSIENT_SMTP_ERRORS).
- Are idempotent: re-running the same task with the same args is safe.

Usage:
    from apps.common.email_tasks import (
        task_send_welcome_email,
        task_send_password_reset_email,
        ...
    )
    task_send_welcome_email.delay(user_id=42)
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {"max_retries": 3, "countdown": 30}  # 30s → 1min → 2min
_TRANSIENT_BASES: tuple = ()  # populated lazily to avoid import at module load


def _transient_errors() -> tuple:
    global _TRANSIENT_BASES
    if not _TRANSIENT_BASES:
        import smtplib, socket
        _TRANSIENT_BASES = (
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
            ConnectionRefusedError,
            ConnectionResetError,
            TimeoutError,
            socket.timeout,
            OSError,
        )
    return _TRANSIENT_BASES


# ---------------------------------------------------------------------------
# STUDENT-FACING TASKS
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_welcome_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_welcome_email(self, user_id: int) -> None:
    from apps.users.models import User
    from apps.common.email_service import send_welcome_email
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("task_send_welcome_email: user %s not found", user_id)
        return
    send_welcome_email(user)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_password_reset_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_password_reset_email(self, user_id: int, reset_url: str) -> None:
    from apps.users.models import User
    from apps.common.email_service import send_password_reset_email
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("task_send_password_reset_email: user %s not found", user_id)
        return
    send_password_reset_email(user, reset_url)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_school_assigned_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_school_assigned_email(
    self,
    student_id: int,
    school_id: int,
    assigned_by_id: int | None = None,
    course_id: int | None = None,
) -> None:
    from apps.crm.models import Student, School, Course
    from apps.users.models import User
    from apps.common.email_service import send_school_assigned_email
    try:
        student = Student.objects.get(pk=student_id)
        school = School.objects.get(pk=school_id)
    except Exception as exc:
        logger.warning("task_send_school_assigned_email: lookup failed — %s", exc)
        return
    assigned_by = User.objects.filter(pk=assigned_by_id).first() if assigned_by_id else None
    course = Course.objects.filter(pk=course_id).first() if course_id else None
    send_school_assigned_email(student, school, assigned_by=assigned_by, course=course)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_student_staff_assignment_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_student_staff_assignment_email(
    self, student_id: int, staff_id: int, role_label: str
) -> None:
    from apps.crm.models import Student
    from apps.users.models import User
    from apps.common.email_service import send_student_staff_assignment_email
    try:
        student = Student.objects.get(pk=student_id)
        staff = User.objects.get(pk=staff_id)
    except Exception as exc:
        logger.warning("task_send_student_staff_assignment_email: lookup failed — %s", exc)
        return
    send_student_staff_assignment_email(student, staff, role_label)


# ---------------------------------------------------------------------------
# STAFF-FACING TASKS
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_staff_invite_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_staff_invite_email(self, invite_id: int) -> None:
    from apps.common.email_service import send_staff_invite_email
    try:
        from apps.users.models import StaffInvite
        invite = StaffInvite.objects.get(pk=invite_id)
    except Exception as exc:
        logger.warning("task_send_staff_invite_email: invite %s not found — %s", invite_id, exc)
        return
    send_staff_invite_email(invite)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_staff_onboarding_email",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_staff_onboarding_email(self, user_id: int) -> None:
    from apps.users.models import User
    from apps.common.email_service import send_staff_onboarding_email
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("task_send_staff_onboarding_email: user %s not found", user_id)
        return
    send_staff_onboarding_email(user)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_assignment_notification",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_assignment_notification(
    self, staff_id: int, student_id: int, role_label: str
) -> None:
    from apps.users.models import User
    from apps.crm.models import Student
    from apps.common.email_service import send_assignment_email
    try:
        staff = User.objects.get(pk=staff_id)
        student = Student.objects.get(pk=student_id)
    except Exception as exc:
        logger.warning("task_send_assignment_notification: lookup failed — %s", exc)
        return
    send_assignment_email(staff, student, role_label)


@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_doc_uploaded_by_student",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_doc_uploaded_by_student(
    self, doc_id: int, recipient_id: int, is_reminder: bool = False, hours_elapsed: int = 0
) -> None:
    from apps.users.models import User
    from apps.common.email_service import send_doc_uploaded_by_student_email
    try:
        from apps.crm.models import StudentSchoolDocument
        doc = StudentSchoolDocument.objects.select_related("student", "school").get(pk=doc_id)
        recipient = User.objects.get(pk=recipient_id)
    except Exception as exc:
        logger.warning("task_send_doc_uploaded_by_student: lookup failed — %s", exc)
        return
    send_doc_uploaded_by_student_email(doc, recipient, is_reminder=is_reminder, hours_elapsed=hours_elapsed)


# ---------------------------------------------------------------------------
# ADMIN ALERT TASKS
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="apps.common.email_tasks.send_high_risk_alert",
    ignore_result=True,
    autoretry_for=_transient_errors(),
    retry_kwargs=_RETRY_KWARGS,
)
def task_send_high_risk_alert(
    self,
    event_description: str,
    ip_address: str = "",
    user_email: str = "",
    extra: dict | None = None,
) -> None:
    from apps.common.email_service import send_high_risk_alert
    send_high_risk_alert(event_description, ip_address=ip_address, user_email=user_email, extra=extra)
