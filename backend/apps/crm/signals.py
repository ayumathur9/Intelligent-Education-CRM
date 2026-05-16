from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.audit.services import log_activity

from .models import Course, Enquiry, FollowUp, Lead, Student


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


def _actor_from_instance(instance):
    # For create/update from API we also set created_by in views; signals fallback to that.
    return getattr(instance, "created_by", None) or getattr(instance, "assigned_to", None)


@receiver(post_save, sender=Lead)
def lead_saved(sender, instance: Lead, created: bool, **kwargs):
    log_activity(actor=_actor_from_instance(instance), action="lead.created" if created else "lead.updated", instance=instance)


@receiver(post_delete, sender=Lead)
def lead_deleted(sender, instance: Lead, **kwargs):
    log_activity(actor=_actor_from_instance(instance), action="lead.deleted", instance=instance)


@receiver(post_save, sender=Student)
def student_saved(sender, instance: Student, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="student.created" if created else "student.updated",
        instance=instance,
    )


@receiver(post_save, sender=Course)
def course_saved(sender, instance: Course, created: bool, **kwargs):
    log_activity(actor=None, action="course.created" if created else "course.updated", instance=instance)


@receiver(post_save, sender=Enquiry)
def enquiry_saved(sender, instance: Enquiry, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="enquiry.created" if created else "enquiry.updated",
        instance=instance,
    )


@receiver(post_save, sender=FollowUp)
def followup_saved(sender, instance: FollowUp, created: bool, **kwargs):
    log_activity(
        actor=_actor_from_instance(instance),
        action="followup.created" if created else "followup.updated",
        instance=instance,
    )

