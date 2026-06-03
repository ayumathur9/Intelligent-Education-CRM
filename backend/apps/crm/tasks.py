"""Celery tasks for the CRM app — document upload notifications."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.crm.tasks.notify_editor_doc_uploaded",
    ignore_result=True,
)
def notify_editor_doc_uploaded(self, doc_id: int, is_reminder: bool = False, hours_elapsed: int = 0) -> None:
    """
    Notify the student's editor (and counselor if no editor) when a student uploads
    a school document. Called immediately, then again at 24h and 48h if unacknowledged.
    """
    from apps.crm.models import StudentSchoolDocument
    from apps.common.email_service import send_doc_uploaded_by_student_email

    try:
        doc = StudentSchoolDocument.objects.select_related(
            "student__editor", "student__counselor", "school"
        ).get(pk=doc_id, deleted_at__isnull=True)
    except StudentSchoolDocument.DoesNotExist:
        logger.warning("notify_editor_doc_uploaded: doc %s not found or deleted", doc_id)
        return

    student = doc.student
    # Prefer editor; fall back to counselor.
    recipient = student.editor or student.counselor
    if not recipient:
        logger.info("notify_editor_doc_uploaded: no editor/counselor for student %s", student.pk)
        return

    send_doc_uploaded_by_student_email(doc, recipient, is_reminder=is_reminder, hours_elapsed=hours_elapsed)
    logger.info(
        "notify_editor_doc_uploaded: sent to %s for doc %s (reminder=%s, hours=%s)",
        recipient.email, doc_id, is_reminder, hours_elapsed,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="apps.crm.tasks.notify_student_doc_uploaded",
    ignore_result=True,
)
def notify_student_doc_uploaded(self, doc_id: int, uploader_id: int, uploader_role: str) -> None:
    """
    Notify the student and their POC when a staff member uploads a school document.
    """
    from apps.crm.models import StudentSchoolDocument
    from apps.users.models import User
    from apps.common.email_service import send_doc_uploaded_by_staff_email

    try:
        doc = StudentSchoolDocument.objects.select_related(
            "student__poc", "school"
        ).get(pk=doc_id, deleted_at__isnull=True)
    except StudentSchoolDocument.DoesNotExist:
        logger.warning("notify_student_doc_uploaded: doc %s not found or deleted", doc_id)
        return

    try:
        uploader = User.objects.get(pk=uploader_id)
    except User.DoesNotExist:
        uploader = None

    send_doc_uploaded_by_staff_email(doc, uploader, uploader_role)
    logger.info("notify_student_doc_uploaded: sent for doc %s by user %s", doc_id, uploader_id)
