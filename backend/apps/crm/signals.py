from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.audit.services import log_activity

from .models import Course, Enquiry, FollowUp, Lead, School, Student, StudentAssignedSchool, StudentSchoolDocument


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def auto_create_student_profile(sender, instance, created: bool, **kwargs):
    """Auto-create a crm_student record when a user with role 'student' is created."""
    if not created:
        return
    if getattr(instance, "role", None) != "student":
        return
    if Student.objects.filter(user=instance).exists():
        return
    # student_code is auto-assigned in Student.save()
    Student.objects.create(
        user=instance,
        full_name=instance.full_name or instance.email,
        email=instance.email,
    )
    # Send welcome email for admin-created students who are already verified.
    # Self-registered students are handled by RegisterView (no-verify path) or
    # EmailVerifyView (verification-required path).
    if getattr(instance, "is_email_verified", False):
        try:
            from apps.users.tasks import send_welcome_email_task
            send_welcome_email_task.delay(instance.pk)
        except Exception:
            try:
                from apps.common.email_service import send_welcome_email
                send_welcome_email(instance)
            except Exception:
                pass


def _actor_from_instance(instance):
    return getattr(instance, "created_by", None) or getattr(instance, "assigned_to", None)


# ── Student assignment tracking ──────────────────────────────────────────────

@receiver(pre_save, sender=Student)
def student_pre_save(sender, instance: Student, **kwargs):
    """Capture old counselor/editor/poc IDs before save so we can detect changes."""
    if not instance.pk:
        instance._pre_counselor_id = None
        instance._pre_editor_id = None
        instance._pre_poc_id = None
        return
    try:
        old = Student.objects.get(pk=instance.pk)
        instance._pre_counselor_id = old.counselor_id
        instance._pre_editor_id = old.editor_id
        instance._pre_poc_id = old.poc_id
    except Student.DoesNotExist:
        instance._pre_counselor_id = None
        instance._pre_editor_id = None
        instance._pre_poc_id = None


@receiver(post_save, sender=Student)
def student_saved(sender, instance: Student, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="student.created" if created else "student.updated",
        instance=instance,
    )
    _send_assignment_emails(instance)
    # INFRA-003: invalidate cached dashboard aggregates on any student change.
    from apps.crm.services.cache_service import invalidate_dashboard_cache
    invalidate_dashboard_cache()


def _send_assignment_emails(instance: Student) -> None:
    from apps.common.email_service import send_assignment_email, send_student_staff_assignment_email

    checks = [
        ("counselor", instance.counselor, getattr(instance, "_pre_counselor_id", None), "Counselor"),
        ("editor", instance.editor, getattr(instance, "_pre_editor_id", None), "Editor"),
        ("poc", instance.poc, getattr(instance, "_pre_poc_id", None), "Point of Contact"),
    ]
    for _field, staff_user, old_id, label in checks:
        if staff_user and staff_user.pk != old_id:
            # Notify the staff member of the new assignment.
            send_assignment_email(staff_user, instance, label)
            # Notify the student that someone has been assigned to them.
            send_student_staff_assignment_email(instance, staff_user, label)


# ── Other model signals ──────────────────────────────────────────────────────

@receiver(post_save, sender=Lead)
def lead_saved(sender, instance: Lead, created: bool, **kwargs):
    log_activity(actor=_actor_from_instance(instance), action="lead.created" if created else "lead.updated", instance=instance)
    from apps.crm.services.cache_service import invalidate_dashboard_cache
    invalidate_dashboard_cache()


@receiver(post_delete, sender=Lead)
def lead_deleted(sender, instance: Lead, **kwargs):
    log_activity(actor=_actor_from_instance(instance), action="lead.deleted", instance=instance)
    from apps.crm.services.cache_service import invalidate_dashboard_cache
    invalidate_dashboard_cache()


@receiver(post_save, sender=Course)
def course_saved(sender, instance: Course, created: bool, **kwargs):
    log_activity(actor=None, action="course.created" if created else "course.updated", instance=instance)
    from apps.crm.services.cache_service import invalidate_dashboard_cache
    invalidate_dashboard_cache()


@receiver(post_save, sender=School)
def school_saved(sender, instance: School, created: bool, **kwargs):
    # INFRA-003: invalidate school list cache on any change.
    from apps.crm.services.cache_service import invalidate_school_cache
    invalidate_school_cache()


@receiver(post_delete, sender=School)
def school_deleted(sender, instance: School, **kwargs):
    from apps.crm.services.cache_service import invalidate_school_cache
    invalidate_school_cache()


@receiver(post_save, sender=Enquiry)
def enquiry_saved(sender, instance: Enquiry, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="enquiry.created" if created else "enquiry.updated",
        instance=instance,
    )


@receiver(post_save, sender=StudentSchoolDocument)
def school_document_saved(sender, instance: StudentSchoolDocument, created: bool, **kwargs):
    """Fire document upload notification emails on new (non-deleted) uploads only."""
    if not created:
        return
    if instance.deleted_at is not None:
        return

    uploader = instance.uploaded_by
    uploader_role = getattr(uploader, "role", "") if uploader else ""

    # Determine if uploaded by student or staff
    is_student_upload = (uploader_role == "student") or (
        uploader is None and instance.category in ("additional_student",)
    )

    from apps.crm.tasks import notify_editor_doc_uploaded, notify_student_doc_uploaded

    if is_student_upload:
        # Immediate notification to editor/counselor
        notify_editor_doc_uploaded.delay(instance.pk, is_reminder=False, hours_elapsed=0)
        # 24-hour follow-up
        notify_editor_doc_uploaded.apply_async(
            args=[instance.pk, True, 24],
            countdown=24 * 3600,
        )
        # 48-hour follow-up
        notify_editor_doc_uploaded.apply_async(
            args=[instance.pk, True, 48],
            countdown=48 * 3600,
        )
    else:
        # Staff uploaded — notify student + POC
        role_labels = {"counselor": "Counselor", "editor": "Editor", "admin": "Admin"}
        role_label = role_labels.get(uploader_role, uploader_role.title() if uploader_role else "Staff")
        uploader_id = uploader.pk if uploader else 0
        notify_student_doc_uploaded.delay(instance.pk, uploader_id, role_label)


@receiver(post_save, sender=StudentAssignedSchool)
def school_assigned_to_student(sender, instance: StudentAssignedSchool, created: bool, **kwargs):
    """Notify the student when a school is assigned to their application."""
    if not created:
        return
    try:
        from apps.common.email_service import send_school_assigned_email
        send_school_assigned_email(
            student=instance.student,
            school=instance.school,
            assigned_by=instance.assigned_by,
            course=instance.course,
        )
    except Exception:
        pass


@receiver(post_save, sender=FollowUp)
def followup_saved(sender, instance: FollowUp, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="followup.created" if created else "followup.updated",
        instance=instance,
    )
    # INFRA-003: invalidate followup_due count so the dashboard reflects changes immediately.
    from apps.crm.services.cache_service import invalidate_dashboard_cache
    invalidate_dashboard_cache()
