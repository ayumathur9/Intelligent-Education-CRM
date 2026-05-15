from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.crm.models import Course, Enquiry, FollowUp, Lead, Student
from apps.users.models import Role, User


class Command(BaseCommand):
    help = "Seed demo data for Intelligent Education CRM"

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(
            email="admin@intelligent-edu.local",
            defaults={"full_name": "Admin User", "role": Role.ADMIN, "is_staff": True, "is_superuser": True},
        )
        admin.set_password("Admin@123456")
        admin.is_staff = True
        admin.is_superuser = True
        admin.role = Role.ADMIN
        admin.save(update_fields=["password", "is_staff", "is_superuser", "role"])

        counselor, _ = User.objects.get_or_create(
            email="counselor@intelligent-edu.local",
            defaults={"full_name": "Counselor User", "role": Role.COUNSELOR, "is_staff": True},
        )
        counselor.set_password("Counselor@123456")
        counselor.is_staff = True
        counselor.role = Role.COUNSELOR
        counselor.save(update_fields=["password", "is_staff", "role"])

        student_user, _ = User.objects.get_or_create(
            email="student@intelligent-edu.local",
            defaults={"full_name": "Student User", "role": Role.STUDENT},
        )
        student_user.set_password("Student@123456")
        student_user.role = Role.STUDENT
        student_user.save(update_fields=["password", "role"])

        course, _ = Course.objects.get_or_create(
            code="PY-FS-01",
            defaults={"name": "Python Full-Stack", "duration_weeks": 16, "fee_amount": 25000, "is_active": True},
        )

        lead, _ = Lead.objects.get_or_create(
            email="lead1@example.com",
            defaults={
                "full_name": "Rahul Sharma",
                "phone": "9999999999",
                "source": "website",
                "course_interested": course,
                "assigned_to": counselor,
                "created_by": admin,
                "notes": "Interested in weekday batch.",
            },
        )

        student, _ = Student.objects.get_or_create(
            student_code="IE-STU-0001",
            defaults={
                "user": student_user,
                "full_name": student_user.full_name,
                "phone": "8888888888",
                "email": student_user.email,
                "course": course,
                "joined_on": timezone.localdate(),
                "is_active": True,
            },
        )

        enquiry, _ = Enquiry.objects.get_or_create(
            subject="Fee structure and timing",
            lead=lead,
            defaults={
                "message": "Please share fee breakdown and class timings.",
                "assigned_to": counselor,
                "created_by": admin,
            },
        )

        FollowUp.objects.get_or_create(
            enquiry=enquiry,
            defaults={
                "scheduled_at": timezone.now() + timedelta(days=1),
                "note": "Call and explain fee + timings.",
                "assigned_to": counselor,
                "created_by": admin,
            },
        )

        self.stdout.write(self.style.SUCCESS("Seed data created."))
        self.stdout.write("Admin login: admin@intelligent-edu.local / Admin@123456")
        self.stdout.write("Counselor login: counselor@intelligent-edu.local / Counselor@123456")
        self.stdout.write("Student login: student@intelligent-edu.local / Student@123456")

