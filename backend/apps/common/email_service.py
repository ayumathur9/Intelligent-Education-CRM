from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)


def _send(subject: str, text_body: str, html_body: str, to: list[str]) -> bool:
    if not _smtp_configured():
        logger.warning("Email not sent to %s — SMTP not configured (EMAIL_HOST_USER/PASSWORD missing)", to)
        return False
    if not to:
        return False
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email to %s (subject: %s)", to, subject)
        return False


def send_welcome_email(user) -> bool:
    context = {
        "full_name": user.full_name or user.email,
        "email": user.email,
        "login_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login.html",
    }
    html_body = render_to_string("emails/welcome.html", context)
    text_body = (
        f"Hi {context['full_name']},\n\n"
        "Welcome to Intelligent Education CRM.\n\n"
        f"Log in here: {context['login_url']}\n\n"
        "— The Intelligent Education Team"
    )
    return _send(
        subject="Welcome to Intelligent Education CRM",
        text_body=text_body,
        html_body=html_body,
        to=[user.email],
    )


def send_password_reset_email(user, reset_url: str) -> bool:
    context = {
        "full_name": user.full_name or user.email,
        "reset_url": reset_url,
    }
    html_body = render_to_string("emails/password_reset.html", context)
    text_body = (
        f"Hi {context['full_name']},\n\n"
        "Use the link below to reset your password (expires in 30 minutes):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, ignore this email.\n\n"
        "— The Intelligent Education Team"
    )
    return _send(
        subject="Reset your Intelligent Education password",
        text_body=text_body,
        html_body=html_body,
        to=[user.email],
    )


def send_assignment_email(staff_user, student, role_label: str) -> bool:
    """Notify a staff member that a student has been assigned to them."""
    if not staff_user or not staff_user.email:
        return False
    context = {
        "staff_name": staff_user.full_name or staff_user.email,
        "role_label": role_label,
        "student_name": student.full_name or student.student_code,
        "student_code": student.student_code,
        "student_email": student.email,
        "dashboard_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/admin_dashboard/code.html",
    }
    html_body = render_to_string("emails/assignment_notification.html", context)
    text_body = (
        f"Hi {context['staff_name']},\n\n"
        f"You have been assigned as {role_label} for student "
        f"{context['student_name']} ({context['student_code']}).\n\n"
        f"Student email: {context['student_email']}\n\n"
        f"Log in to the dashboard: {context['dashboard_url']}\n\n"
        "— The Intelligent Education Team"
    )
    return _send(
        subject=f"[Intelligent Education] Student assigned to you — {context['student_name']}",
        text_body=text_body,
        html_body=html_body,
        to=[staff_user.email],
    )
