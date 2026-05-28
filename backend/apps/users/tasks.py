"""Celery tasks for the users app — ASYNC-002."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.users.tasks.send_welcome_email",
    ignore_result=True,
)
def send_welcome_email_task(self, user_id: int) -> None:
    """Send welcome email asynchronously after user registration."""
    from apps.users.models import User
    from apps.common.email_service import send_welcome_email

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("send_welcome_email: user %s not found", user_id)
        return

    send_welcome_email(user)
    logger.info("Welcome email sent to user %s", user_id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.users.tasks.send_password_reset_email",
    ignore_result=True,
)
def send_password_reset_email_task(self, user_id: int, reset_link: str) -> None:
    """Send password reset email asynchronously."""
    from apps.users.models import User
    from apps.common.email_service import send_password_reset_email

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("send_password_reset_email: user %s not found", user_id)
        return

    send_password_reset_email(user, reset_link)
    logger.info("Password reset email dispatched for user %s", user_id)


@shared_task(
    bind=True,
    name="apps.users.tasks.purge_expired_tokens",
    ignore_result=True,
)
def purge_expired_tokens(self) -> None:
    """
    Daily maintenance: delete expired JWT blacklist entries.
    Prevents unbounded table growth on the token_blacklist tables.
    """
    from django.utils import timezone
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    cutoff = timezone.now()
    expired_qs = OutstandingToken.objects.filter(expires_at__lt=cutoff)
    token_ids = list(expired_qs.values_list("id", flat=True))

    if token_ids:
        BlacklistedToken.objects.filter(token_id__in=token_ids).delete()
        deleted_count, _ = expired_qs.delete()
        logger.info("Purged %d expired JWT outstanding tokens", deleted_count)
    else:
        logger.info("purge_expired_tokens: nothing to purge")


@shared_task(
    bind=True,
    name="apps.users.tasks.cleanup_expired_reset_tokens",
    ignore_result=True,
)
def cleanup_expired_reset_tokens(self) -> None:
    """Daily maintenance: delete expired/used PasswordResetToken records."""
    from django.utils import timezone
    from apps.users.models import PasswordResetToken

    cutoff = timezone.now()
    deleted, _ = PasswordResetToken.objects.filter(expires_at__lt=cutoff).delete()
    logger.info("cleanup_expired_reset_tokens: deleted %d expired tokens", deleted)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.users.tasks.send_staff_onboarding_email",
    ignore_result=True,
)
def send_staff_onboarding_email_task(self, user_id: int) -> None:
    """Send staff onboarding email asynchronously after account creation."""
    from apps.users.models import User
    from apps.common.email_service import send_staff_onboarding_email

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("send_staff_onboarding_email: user %s not found", user_id)
        return

    send_staff_onboarding_email(user)
    logger.info("Staff onboarding email sent to user %s", user_id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.users.tasks.send_staff_invite_email",
    ignore_result=True,
)
def send_staff_invite_email_task(self, invite_id: int) -> None:
    """Send staff invite email asynchronously."""
    from apps.users.models import StaffInvite
    from apps.common.email_service import send_staff_invite_email

    try:
        invite = StaffInvite.objects.get(pk=invite_id)
    except StaffInvite.DoesNotExist:
        logger.warning("send_staff_invite_email: invite %s not found", invite_id)
        return

    send_staff_invite_email(invite)
    logger.info("Staff invite email sent to %s (invite_id=%s)", invite.email, invite_id)


@shared_task(
    bind=True,
    name="apps.users.tasks.send_assignment_email",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def send_assignment_email_task(self, staff_user_id: int, student_id: int, role_label: str) -> None:
    """Notify staff member of a student assignment, asynchronously."""
    from apps.users.models import User
    from apps.crm.models import Student
    from apps.common.email_service import send_assignment_email

    try:
        staff_user = User.objects.get(pk=staff_user_id)
        student = Student.objects.get(pk=student_id)
    except (User.DoesNotExist, Student.DoesNotExist) as exc:
        logger.warning("send_assignment_email: lookup failed — %s", exc)
        return

    send_assignment_email(staff_user, student, role_label)
    logger.info("Assignment email sent: staff=%s student=%s", staff_user_id, student_id)
