from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from apps.crm.models import Student


# Fields grouped by section: (field_name, human_label)
REQUIRED_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Personal Details", [
        ("dob", "Date of birth"),
        ("gender", "Gender"),
        ("nationality", "Nationality"),
        ("country_of_birth", "Country of birth"),
        ("native_language", "Native language"),
    ]),
    ("Passport", [
        ("passport_name", "Name on passport"),
        ("passport_number", "Passport number"),
        ("passport_issue_date", "Passport issue date"),
        ("passport_expiry_date", "Passport expiry date"),
    ]),
    ("Permanent Address", [
        ("perm_line_1", "Address line 1"),
        ("perm_city", "City"),
        ("perm_state", "State / Province"),
        ("perm_country", "Country"),
        ("perm_postcode", "Postcode"),
    ]),
    ("Father's Details", [
        ("father_name", "Father's name"),
        ("father_phone", "Father's phone"),
        ("father_email", "Father's email"),
    ]),
    ("Mother's Details", [
        ("mother_name", "Mother's name"),
        ("mother_phone", "Mother's phone"),
        ("mother_email", "Mother's email"),
    ]),
    ("Emergency Contact", [
        ("emergency_name", "Contact name"),
        ("emergency_relationship", "Relationship"),
        ("emergency_mobile", "Mobile number"),
    ]),
]


def _missing_sections(student: Student) -> list[tuple[str, list[str]]]:
    """Return sections that have at least one empty required field."""
    result = []
    for section_name, fields in REQUIRED_SECTIONS:
        missing = []
        for field_name, label in fields:
            value = getattr(student, field_name, None)
            if not value:
                missing.append(label)
        if missing:
            result.append((section_name, missing))

    # Education history — must have at least one record
    if not student.education_history.exists():
        result.append(("Education History", ["At least one education record required"]))

    return result


def _send_reminder(student: Student, missing: list[tuple[str, list[str]]], dry_run: bool) -> None:
    recipient = student.email
    context = {
        "student_name": student.full_name or student.student_code,
        "missing_sections": missing,
        "login_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login/",
    }
    html_body = render_to_string("emails/profile_reminder.html", context)
    text_body = _plain_text(student, missing)

    if dry_run:
        return

    msg = EmailMultiAlternatives(
        subject="Action required: complete your profile",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def _plain_text(student: Student, missing: list[tuple[str, list[str]]]) -> str:
    lines = [
        f"Hi {student.full_name or student.student_code},",
        "",
        "Your Intelligent Education profile has incomplete sections.",
        "Please log in and fill in the following:",
        "",
    ]
    for section, fields in missing:
        lines.append(f"  {section}:")
        for f in fields:
            lines.append(f"    - {f}")
        lines.append("")
    lines += [
        f"Log in here: {settings.FRONTEND_BASE_URL.rstrip('/')}/login/",
        "",
        "— The Intelligent Education Team",
    ]
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Send weekly profile-completion reminder emails to active students with missing fields"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check and report missing fields without sending any emails",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        if not dry_run and not (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD):
            self.stderr.write(self.style.ERROR(
                "EMAIL_HOST_USER or EMAIL_HOST_PASSWORD not set. Use --dry-run to test without sending."
            ))
            return

        students = (
            Student.objects.filter(is_active=True)
            .exclude(email="")
            .prefetch_related("education_history")
            .select_related("course")
        )

        sent = skipped = errors = 0

        for student in students:
            missing = _missing_sections(student)
            if not missing:
                skipped += 1
                continue

            label = "[DRY RUN] " if dry_run else ""
            self.stdout.write(f"{label}{student.student_code} ({student.email}): {len(missing)} section(s) incomplete")

            if dry_run:
                for section, fields in missing:
                    self.stdout.write(f"  {section}: {', '.join(fields)}")
                sent += 1
                continue

            try:
                _send_reminder(student, missing, dry_run=False)
                self.stdout.write(self.style.SUCCESS(f"  Reminder sent"))
                sent += 1
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  Failed: {exc}"))
                errors += 1

        action = "Would notify" if dry_run else "Notified"
        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {action} {sent} student(s). Skipped {skipped} (complete profiles). Errors: {errors}."
        ))
