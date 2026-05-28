from __future__ import annotations

import logging
import smtplib
import socket

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# MED-5: Only retry on transient SMTP errors (network issues, temp unavailability).
# Don't retry on permanent errors (auth failure, bad recipient, etc.).
_TRANSIENT_SMTP_ERRORS = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    socket.timeout,
    OSError,
)


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
    except _TRANSIENT_SMTP_ERRORS:
        # Transient failure — Celery will retry via the task wrapper.
        logger.warning("Transient SMTP error sending to %s — will retry", to)
        raise
    except Exception:
        # Permanent failure (bad credentials, invalid recipient, etc.) — don't retry.
        logger.exception("Permanent email failure to %s (subject: %s) — not retrying", to, subject)
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


_BROADCAST_CONFIGS = {
    "maintenance": {
        "header_icon": "&#128736;",
        "header_title": "Scheduled Maintenance Notice",
        "header_subtitle": "Planned downtime — please read carefully",
    },
    "incident": {
        "header_icon": "&#9888;",
        "header_title": "Incident Status Update",
        "header_subtitle": "We are currently experiencing an issue",
    },
    "restored": {
        "header_icon": "&#10003;",
        "header_title": "Service Restored",
        "header_subtitle": "All systems are back to normal",
    },
    "general": {
        "header_icon": "&#128226;",
        "header_title": "Important Notice",
        "header_subtitle": "Message from Intelligent Education",
    },
}

_BROADCAST_SUBJECTS = {
    "maintenance": "[Intelligent Education] Scheduled Maintenance Notice",
    "incident": "[Intelligent Education] Incident Update — Platform Issue",
    "restored": "[Intelligent Education] Service Restored",
    "general": "[Intelligent Education] Important Notice",
}


def send_broadcast_email(
    broadcast_type: str,
    body_message: str,
    recipients: list[str],
    sent_by: str = "Intelligent Education Admin",
    meta_fields: dict | None = None,
    custom_subject: str = "",
) -> bool:
    """
    Send a broadcast email (maintenance/incident/restored/general) to a list of recipients.
    Called manually from the admin broadcast endpoint.
    """
    from django.utils import timezone as _tz
    config = _BROADCAST_CONFIGS.get(broadcast_type, _BROADCAST_CONFIGS["general"])
    subject = custom_subject or _BROADCAST_SUBJECTS.get(broadcast_type, "[Intelligent Education] Notice")
    sent_at = _tz.now().strftime("%d %b %Y, %H:%M UTC")
    context = {
        "broadcast_type": broadcast_type,
        "header_icon": config["header_icon"],
        "header_title": config["header_title"],
        "header_subtitle": config["header_subtitle"],
        "body_message": body_message,
        "meta_fields": meta_fields or {},
        "sent_by": sent_by,
        "sent_at": sent_at,
        "subject": subject,
    }
    html_body = render_to_string("emails/broadcast.html", context)
    text_body = f"{config['header_title']}\n\n{body_message}\n\n— {sent_by} ({sent_at})"
    return _send(subject=subject, text_body=text_body, html_body=html_body, to=recipients)


def _get_admin_emails() -> list[str]:
    """Return email addresses of all active admin users."""
    try:
        from apps.users.models import User, Role
        return list(
            User.objects.filter(role=Role.ADMIN, is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )
    except Exception:
        fallback = settings.DEFAULT_FROM_EMAIL
        # Strip display name if present (e.g. "Name <email@x.com>" → "email@x.com")
        if "<" in fallback:
            fallback = fallback.split("<")[-1].strip(">").strip()
        return [fallback]


def _send_admin_alert(
    alert_type: str,
    alert_subtitle: str,
    alert_intro: str,
    severity: str,
    details: dict,
    stack_trace: str = "",
    recommended_actions: list[str] | None = None,
    incident_id: str = "",
) -> bool:
    """Internal helper: render the shared admin_alert.html template and send to all admins."""
    from django.utils import timezone as _tz
    occurred_at = _tz.now().strftime("%d %b %Y, %H:%M UTC")
    context = {
        "alert_type": alert_type,
        "alert_subtitle": alert_subtitle,
        "alert_intro": alert_intro,
        "severity": severity,
        "details": details,
        "stack_trace": stack_trace,
        "recommended_actions": recommended_actions or [],
        "incident_id": incident_id,
        "occurred_at": occurred_at,
        "dashboard_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/admin_dashboard/code.html",
    }
    html_body = render_to_string("emails/admin_alert.html", context)
    text_lines = [f"[{severity.upper()}] {alert_type}", f"Time: {occurred_at}", ""]
    for k, v in details.items():
        text_lines.append(f"{k}: {v}")
    if stack_trace:
        text_lines += ["", "Error log:", stack_trace[:1000]]
    if recommended_actions:
        text_lines += ["", "Recommended actions:"] + [f"- {a}" for a in recommended_actions]
    text_body = "\n".join(text_lines)
    admins = _get_admin_emails()
    if not admins:
        logger.warning("_send_admin_alert: no admin email recipients found for alert '%s'", alert_type)
        return False
    return _send(
        subject=f"[IE Admin Alert] [{severity.upper()}] {alert_type}",
        text_body=text_body,
        html_body=html_body,
        to=admins,
    )


def send_high_risk_alert(event_description: str, ip_address: str = "", user_email: str = "", extra: dict | None = None) -> bool:
    """Alert admins of a security anomaly (brute force, unusual login, etc.)."""
    details: dict = {"Event": event_description}
    if ip_address:
        details["IP Address"] = ip_address
    if user_email:
        details["User Email"] = user_email
    if extra:
        details.update(extra)
    return _send_admin_alert(
        alert_type="High-Risk Activity Detected",
        alert_subtitle="A security anomaly has been detected on the platform",
        alert_intro=(
            "The Intelligent Education security system has flagged a potentially malicious or unusual event. "
            "Please review the details below and take action if required."
        ),
        severity="critical",
        details=details,
        recommended_actions=[
            "Review the flagged account and consider temporary suspension.",
            "Check audit logs for further suspicious activity from this IP.",
            "If brute force is confirmed, ensure IP is rate-limited or blocked.",
            "Notify the account owner if credentials may have been compromised.",
        ],
    )


def send_backup_failure_alert(error_message: str, severity: str = "high") -> bool:
    """Alert admins when a scheduled database backup fails."""
    from django.utils import timezone as _tz
    return _send_admin_alert(
        alert_type="Backup Failure",
        alert_subtitle="Scheduled database backup did not complete successfully",
        alert_intro=(
            "The nightly database backup job has failed. Immediate attention is required "
            "to ensure data recovery capabilities are not compromised."
        ),
        severity=severity,
        details={"Error": error_message, "Backup Schedule": "Nightly at 02:00 UTC"},
        recommended_actions=[
            "Check DATABASE_URL and pg_dump availability on the server.",
            "Verify disk space is not exhausted at BACKUP_ROOT.",
            "Re-run the backup manually: python manage.py shell → backup_database.delay()",
            "Escalate to infrastructure team if the issue persists.",
        ],
    )


def send_server_error_alert(exception_type: str, stack_trace: str, incident_id: str = "", path: str = "") -> bool:
    """Alert admins when a critical unhandled server exception occurs."""
    details: dict = {"Exception": exception_type}
    if path:
        details["Request Path"] = path
    return _send_admin_alert(
        alert_type="Server Error Alert",
        alert_subtitle="An unhandled critical exception has occurred",
        alert_intro=(
            "A critical exception was raised in the Intelligent Education CRM application. "
            "Review the stack trace below and resolve the underlying issue."
        ),
        severity="critical",
        details=details,
        stack_trace=stack_trace[:3000],
        incident_id=incident_id,
        recommended_actions=[
            "Review the stack trace and identify the root cause.",
            "Check application logs for context around the error.",
            "If caused by a deployment, consider rolling back.",
            "Monitor for recurrence — if frequent, escalate immediately.",
        ],
    )


def send_escalation_alert(student_name: str, student_code: str, sla_info: str, counselor_name: str = "") -> bool:
    """Alert admins when a student application is delayed beyond SLA."""
    details: dict = {
        "Student": f"{student_name} ({student_code})",
        "SLA Breach": sla_info,
    }
    if counselor_name:
        details["Assigned Counselor"] = counselor_name
    return _send_admin_alert(
        alert_type="Escalation Alert — Application Delayed",
        alert_subtitle="A student application has exceeded the SLA threshold",
        alert_intro=(
            "A student application has not progressed within the expected SLA window. "
            "Please review and escalate to the assigned counselor."
        ),
        severity="high",
        details=details,
        recommended_actions=[
            "Contact the assigned counselor to check the status.",
            "Review the student's application and identify blockers.",
            "Update the application status and log an interaction note.",
            "If no counselor is assigned, assign one immediately.",
        ],
    )


def send_staff_onboarding_email(user) -> bool:
    """Onboarding email sent to counselors, editors, and admins after account creation."""
    role_labels = {"admin": "Admin", "counselor": "Counselor", "editor": "Editor", "student": "Student"}
    role_label = role_labels.get(user.role, user.role.title())
    login_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login.html"
    context = {
        "full_name": user.full_name or user.email,
        "email": user.email,
        "role": user.role,
        "role_label": role_label,
        "login_url": login_url,
    }
    html_body = render_to_string("emails/staff_onboarding.html", context)
    text_body = (
        f"Hi {context['full_name']},\n\n"
        f"Your {role_label} account is ready at Intelligent Education CRM.\n\n"
        f"Log in: {login_url}\n\n"
        "If you have questions, email us at contact.intelligenteducation@gmail.com\n\n"
        "— Intelligent Education"
    )
    return _send(
        subject=f"[Intelligent Education] Welcome to the team — {role_label} account ready",
        text_body=text_body,
        html_body=html_body,
        to=[user.email],
    )


def send_staff_invite_email(invite) -> bool:
    """Send an admin invite to a prospective staff member."""
    from django.conf import settings as _s
    invite_url = f"{_s.FRONTEND_BASE_URL.rstrip('/')}/accept-invite/?token={invite.token}"
    invited_by_name = (
        invite.invited_by.full_name or invite.invited_by.email
        if invite.invited_by else "Intelligent Education Admin"
    )
    role_labels = {"admin": "Admin", "counselor": "Counselor", "editor": "Editor", "student": "Student"}
    role_label = role_labels.get(invite.role, invite.role.title())
    expires_str = invite.expires_at.strftime("%d %b %Y, %H:%M UTC")
    context = {
        "invitee_email": invite.email,
        "invited_by": invited_by_name,
        "role_label": role_label,
        "invite_url": invite_url,
        "expires_at": expires_str,
    }
    html_body = render_to_string("emails/staff_invite.html", context)
    text_body = (
        f"Hi {invite.email},\n\n"
        f"{invited_by_name} has invited you to join Intelligent Education CRM as {role_label}.\n\n"
        f"Accept your invite here (expires {expires_str}):\n{invite_url}\n\n"
        "If you did not expect this, ignore this email.\n\n"
        "— Intelligent Education"
    )
    return _send(
        subject=f"[Intelligent Education] You've been invited as {role_label}",
        text_body=text_body,
        html_body=html_body,
        to=[invite.email],
    )


_DOC_CATEGORY_LABELS = {
    "essay": "Essay",
    "lor": "Letter of Recommendation",
    "resume": "Resume / CV",
    "additional_student": "Additional (Student)",
    "additional_counsel": "Additional (Counsellor)",
}


def send_doc_uploaded_by_student_email(doc, recipient_user, is_reminder: bool = False, hours_elapsed: int = 0) -> bool:
    """Notify editor (or counselor) when a student uploads a school document."""
    if not recipient_user or not recipient_user.email:
        return False
    category_label = _DOC_CATEGORY_LABELS.get(doc.category, doc.category.replace("_", " ").title())
    uploaded_at_str = doc.uploaded_at.strftime("%d %b %Y, %H:%M UTC") if doc.uploaded_at else "—"
    context = {
        "recipient_name": recipient_user.full_name or recipient_user.email,
        "student_name": doc.student.full_name or doc.student.student_code,
        "student_code": doc.student.student_code,
        "school_name": doc.school.name,
        "file_name": doc.file_name,
        "category_label": category_label,
        "uploaded_at": uploaded_at_str,
        "is_reminder": is_reminder,
        "hours_elapsed": hours_elapsed,
        "dashboard_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/admin_dashboard/code.html",
    }
    html_body = render_to_string("emails/doc_uploaded_by_student.html", context)
    reminder_note = f" ({hours_elapsed}h follow-up)" if is_reminder else ""
    text_body = (
        f"Hi {context['recipient_name']},\n\n"
        f"{context['student_name']} uploaded {doc.file_name} for {doc.school.name}.{reminder_note}\n\n"
        f"Review it on the dashboard: {context['dashboard_url']}\n\n"
        "— Intelligent Education"
    )
    subject = (
        f"[IE] {'REMINDER: ' if is_reminder else ''}Document uploaded — {doc.student.full_name or doc.student.student_code}"
    )
    return _send(subject=subject, text_body=text_body, html_body=html_body, to=[recipient_user.email])


def send_doc_uploaded_by_staff_email(doc, uploader_user, uploader_role: str) -> bool:
    """Notify student and POC when a staff member uploads a school document."""
    student = doc.student
    recipients: list[str] = []
    if student.email:
        recipients.append(student.email)
    poc_email = student.poc.email if student.poc and student.poc.email else None
    if poc_email and poc_email not in recipients:
        recipients.append(poc_email)
    if not recipients:
        return False

    category_label = _DOC_CATEGORY_LABELS.get(doc.category, doc.category.replace("_", " ").title())
    uploaded_at_str = doc.uploaded_at.strftime("%d %b %Y, %H:%M UTC") if doc.uploaded_at else "—"
    portal_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/student_application/code.html"
    context = {
        "recipient_name": student.full_name or student.student_code,
        "uploader_name": uploader_user.full_name or uploader_user.email if uploader_user else "Intelligent Education Staff",
        "uploader_role": uploader_role,
        "school_name": doc.school.name,
        "file_name": doc.file_name,
        "category_label": category_label,
        "uploaded_at": uploaded_at_str,
        "portal_url": portal_url,
    }
    html_body = render_to_string("emails/doc_uploaded_by_staff.html", context)
    text_body = (
        f"Hi {context['recipient_name']},\n\n"
        f"{context['uploader_name']} ({uploader_role}) uploaded {doc.file_name} for {doc.school.name}.\n\n"
        f"View it here: {portal_url}\n\n"
        "— Intelligent Education"
    )
    return _send(
        subject=f"[Intelligent Education] Document ready — {doc.file_name}",
        text_body=text_body,
        html_body=html_body,
        to=recipients,
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
        "student_phone": getattr(student, "phone", "") or "",
        "student_course": student.course.name if getattr(student, "course", None) else "",
        "counselor_name": staff_user.full_name or "",
        "counselor_email": staff_user.email or "",
        "counselor_phone": getattr(staff_user, "phone", "") or "",
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
