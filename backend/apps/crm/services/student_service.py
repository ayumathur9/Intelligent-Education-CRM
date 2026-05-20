"""
Student business logic service — PHASE 5 (Architecture refactor).

Centralises all operations that span models, produce side-effects
(audit logs, notifications, emails), or need to be tested independently
of the HTTP layer.

Views should call these functions rather than manipulating models directly.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.crm.models import Student
    from apps.users.models import User

logger = logging.getLogger(__name__)


def soft_delete_student(student: "Student", deleted_by: "User", request=None) -> None:
    """
    Soft-delete a student record.

    - Marks `deleted_at` and sets `is_active=False`
    - Creates an audit log entry with actor IP / user-agent
    - Does NOT hard-delete any related records

    Args:
        student:    The Student instance to delete.
        deleted_by: The User performing the deletion.
        request:    The HTTP request (used to extract IP/user-agent for audit log).

    Raises:
        ValueError: If the student is already deleted.
    """
    from apps.audit.models import ActivityLog

    if student.is_deleted:
        raise ValueError(f"Student {student.student_code} is already deleted.")

    with transaction.atomic():
        student.soft_delete()

        ActivityLog.log(
            action="student_deleted",
            actor=deleted_by,
            entity="Student",
            entity_id=str(student.pk),
            metadata={"student_code": student.student_code, "full_name": student.full_name},
            request=request,
        )

    logger.info(
        "Student %s soft-deleted by user %s", student.student_code, deleted_by.pk
    )


def restore_student(student: "Student", restored_by: "User", request=None) -> None:
    """
    Restore a soft-deleted student.

    Args:
        student:     The Student instance to restore.
        restored_by: The User performing the restoration.
        request:     The HTTP request for audit context.

    Raises:
        ValueError: If the student is not deleted.
    """
    from apps.audit.models import ActivityLog

    if not student.is_deleted:
        raise ValueError(f"Student {student.student_code} is not deleted.")

    with transaction.atomic():
        student.restore()

        ActivityLog.log(
            action="student_restored",
            actor=restored_by,
            entity="Student",
            entity_id=str(student.pk),
            metadata={"student_code": student.student_code},
            request=request,
        )

    logger.info(
        "Student %s restored by user %s", student.student_code, restored_by.pk
    )


def assign_school_to_student(
    *,
    student: "Student",
    school,
    assigned_by: "User",
    course=None,
    notes: str = "",
    deadline=None,
    request=None,
):
    """
    Assign a school to a student with full audit trail.

    Creates an `StudentAssignedSchool` record, writes an audit log, and
    optionally sends a notification to the student.

    Returns:
        The created StudentAssignedSchool instance.

    Raises:
        ValueError: If the student is already assigned to this school.
    """
    from apps.audit.models import ActivityLog
    from apps.crm.models import StudentAssignedSchool

    if StudentAssignedSchool.objects.filter(student=student, school=school).exists():
        raise ValueError(
            f"Student {student.student_code} is already assigned to {school}."
        )

    with transaction.atomic():
        assignment = StudentAssignedSchool.objects.create(
            student=student,
            school=school,
            course=course,
            assigned_by=assigned_by,
            notes=notes,
            deadline=deadline,
        )

        ActivityLog.log(
            action="school_assigned",
            actor=assigned_by,
            entity="Student",
            entity_id=str(student.pk),
            metadata={
                "school_id": school.pk,
                "school_name": str(school),
                "course_id": course.pk if course else None,
            },
            request=request,
        )

    return assignment


def get_students_for_user(user: "User"):
    """
    INFRA-002: Returns an optimised queryset of students visible to the given user.

    Uses select_related and prefetch_related to prevent N+1 queries on
    student list endpoints.

    Role visibility rules:
    - student  → own record only
    - counselor → students where counselor=user
    - editor   → all students (read)
    - admin    → all students
    """
    from apps.crm.models import Student

    base_qs = (
        Student.objects
        .select_related("user", "counselor", "course", "poc", "editor")
        .prefetch_related("assigned_schools__school", "assigned_schools__course")
    )

    role = getattr(user, "role", None)

    if role == "student":
        return base_qs.filter(user=user)

    if role == "counselor":
        return base_qs.filter(counselor=user)

    # admin, editor — full access
    return base_qs
