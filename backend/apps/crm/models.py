from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# LOW-004: E.164-compatible phone validator (shared with users app).
_phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{6,15}$",
    message="Enter a valid phone number (6–15 digits, optional leading +).",
)

# HIGH-005: field-level PII encryption.
# EncryptedCharField is transparent to application code — reads/writes plain text.
# The database stores AES-128 CBC ciphertext.  Requires FIELD_ENCRYPTION_KEY in settings.
try:
    from encrypted_model_fields.fields import EncryptedCharField, EncryptedEmailField
    _ENCRYPTION_AVAILABLE = True
except ImportError:
    # Fallback for environments where the package is not yet installed.
    EncryptedCharField = models.CharField  # type: ignore[misc,assignment]
    EncryptedEmailField = models.EmailField  # type: ignore[misc,assignment]
    _ENCRYPTION_AVAILABLE = False


class LeadStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    QUALIFIED = "qualified", "Qualified"
    LOST = "lost", "Lost"
    CONVERTED = "converted", "Converted"


class EnquiryStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class FollowUpStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DONE = "done", "Done"
    MISSED = "missed", "Missed"


class ActivityType(models.TextChoices):
    APPLICATION_SUBMITTED = "application_submitted", "Application Submitted"
    DOCUMENT_UPLOADED = "document_uploaded", "Document Uploaded"
    MESSAGE_RECEIVED = "message_received", "Message Received"
    PREFERENCE_SAVED = "preference_saved", "Preference Saved"
    PROFILE_UPDATED = "profile_updated", "Profile Updated"
    STATUS_CHANGED = "status_changed", "Status Changed"
    NOTE_ADDED = "note_added", "Note Added"
    MEETING_SCHEDULED = "meeting_scheduled", "Meeting Scheduled"


class DocumentCategory(models.TextChoices):
    ESSAY = "essay", "Essay"
    LOR = "lor", "Letter of Recommendation"
    RESUME = "resume", "Resume / CV"
    ADDITIONAL_STUDENT = "additional_student", "Additional (Student)"
    ADDITIONAL_COUNSELLOR = "additional_counsel", "Additional (Counsellor)"


class ProfileDocumentCategory(models.TextChoices):
    PASSPORT = "passport", "Passport / Identity"
    MARKSHEET_10 = "marksheet_10", "10th Marksheet"
    MARKSHEET_11 = "marksheet_11", "11th Marksheet"
    MARKSHEET_12 = "marksheet_12", "12th Marksheet"
    ENGLISH_PROFICIENCY = "english_proficiency", "English Proficiency (IELTS/PTE)"
    GRE_GMAT_OTHER = "gre_gmat_other", "GRE/GMAT/Other"


class School(models.Model):
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_schools"
    )
    deadline = models.DateField(null=True, blank=True, help_text="General application deadline")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country", "name"]
        indexes = [models.Index(fields=["is_active", "country"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.country})"


class Course(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_weeks = models.PositiveIntegerField(default=0)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, related_name="courses"
    )
    available_countries = models.TextField(
        blank=True, help_text="Comma-separated list of countries where this course is available"
    )
    intake_months = models.CharField(
        max_length=200, blank=True, help_text="e.g. January, May, September"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Lead(models.Model):
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=120, blank=True)
    course_interested = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_leads"
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_leads"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["assigned_to", "status"]),  # INFRA-001: lead pipeline queries
            models.Index(fields=["phone"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        return self.full_name


class ActiveStudentManager(models.Manager):
    """
    MED-010: Default manager that excludes soft-deleted students.
    All querysets via Student.objects will exclude deleted records.
    Use Student.all_objects to access the unfiltered queryset.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Student(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_profile")
    student_code = models.CharField(max_length=40, unique=True, db_index=True)
    full_name = models.CharField(max_length=200)
    # LOW-004: phone validated on API boundary; blank allowed (profile optional).
    phone = models.CharField(max_length=32, blank=True, validators=[_phone_validator])
    email = models.EmailField(blank=True)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="students")
    joined_on = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    counselor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="counseled_students"
    )
    poc = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="poc_students"
    )
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="edited_students"
    )

    class PackSelected(models.TextChoices):
        PREMIUM_MENTORSHIP = "premium_mentorship", "Premium Mentorship"
        FOUNDERS_MENTORSHIP = "founders_mentorship", "Founder's Mentorship"

    pack_selected = models.CharField(
        max_length=30, choices=PackSelected.choices, blank=True, default=""
    )

    # Personal details
    dob = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    gender = models.CharField(max_length=20, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    country_of_birth = models.CharField(max_length=100, blank=True)
    native_language = models.CharField(max_length=100, blank=True)

    # Passport
    passport_name = models.CharField(max_length=200, blank=True)
    # HIGH-005: passport_number encrypted at rest (AES-128 CBC via Fernet key).
    passport_number = EncryptedCharField(max_length=50, blank=True)
    passport_issue_location = models.CharField(max_length=100, blank=True)
    passport_issue_date = models.DateField(null=True, blank=True)
    passport_expiry_date = models.DateField(null=True, blank=True)

    # Permanent address
    perm_country = models.CharField(max_length=100, blank=True)
    perm_line_1 = models.CharField(max_length=200, blank=True)
    perm_line_2 = models.CharField(max_length=200, blank=True)
    perm_city = models.CharField(max_length=100, blank=True)
    perm_state = models.CharField(max_length=100, blank=True)
    perm_postcode = models.CharField(max_length=20, blank=True)

    # Current address
    curr_same_as_perm = models.BooleanField(default=False)
    curr_country = models.CharField(max_length=100, blank=True)
    curr_line_1 = models.CharField(max_length=200, blank=True)
    curr_line_2 = models.CharField(max_length=200, blank=True)
    curr_city = models.CharField(max_length=100, blank=True)
    curr_state = models.CharField(max_length=100, blank=True)
    curr_postcode = models.CharField(max_length=20, blank=True)

    # Father details
    father_name = models.CharField(max_length=200, blank=True)
    father_phone = models.CharField(max_length=32, blank=True, validators=[_phone_validator])
    father_email = models.EmailField(blank=True)
    father_dob = models.DateField(null=True, blank=True)
    father_education = models.CharField(max_length=200, blank=True)
    father_profession = models.CharField(max_length=200, blank=True)
    father_company = models.CharField(max_length=200, blank=True)
    father_position = models.CharField(max_length=200, blank=True)
    # HIGH-005: income figures encrypted at rest.
    father_annual_income = EncryptedCharField(max_length=100, blank=True)

    # Mother details
    mother_name = models.CharField(max_length=200, blank=True)
    mother_phone = models.CharField(max_length=32, blank=True, validators=[_phone_validator])
    mother_email = models.EmailField(blank=True)
    mother_dob = models.DateField(null=True, blank=True)
    mother_education = models.CharField(max_length=200, blank=True)
    mother_profession = models.CharField(max_length=200, blank=True)
    mother_company = models.CharField(max_length=200, blank=True)
    mother_position = models.CharField(max_length=200, blank=True)
    # HIGH-005: income figures encrypted at rest.
    mother_annual_income = EncryptedCharField(max_length=100, blank=True)

    # Emergency contact — encrypted because it links PII to a third-party individual.
    emergency_name = models.CharField(max_length=200, blank=True)
    emergency_relationship = models.CharField(max_length=100, blank=True)
    # HIGH-005: emergency contact details encrypted at rest.
    emergency_mobile = EncryptedCharField(max_length=32, blank=True)
    emergency_email = EncryptedEmailField(blank=True)

    # Destination countries (comma-separated)
    destination_countries = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # MED-010: Soft delete — records are never hard-deleted.
    deleted_at = models.DateTimeField(
        null=True, blank=True, default=None, db_index=True,
        help_text="When set, this student is considered deleted and hidden from all views."
    )

    # MED-010: Default manager excludes soft-deleted records.
    objects = ActiveStudentManager()
    # Unfiltered manager for admin / recovery use.
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "student_code"]),
            models.Index(fields=["counselor", "is_active"]),      # INFRA-001
            models.Index(fields=["deleted_at"]),                  # MED-010
        ]

    def soft_delete(self) -> None:
        """Mark this student as deleted without removing the database row."""
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["deleted_at", "is_active", "updated_at"])

    def restore(self) -> None:
        """Undo a soft delete."""
        self.deleted_at = None
        self.is_active = True
        self.save(update_fields=["deleted_at", "is_active", "updated_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @classmethod
    def _generate_code_locked(cls) -> str:
        """Generate the next student code inside a select_for_update lock."""
        from django.db.models import Max
        last = (
            cls.all_objects.select_for_update()
            .aggregate(Max("student_code"))["student_code__max"]
        )
        if last and last.startswith("STU-") and last[4:].isdigit():
            next_num = int(last[4:]) + 1
        else:
            next_num = 1
        return f"STU-{next_num:04d}"

    def save(self, *args, **kwargs):
        if not self.student_code:
            from django.db import IntegrityError, transaction
            for _ in range(5):
                try:
                    with transaction.atomic():
                        self.student_code = self.__class__._generate_code_locked()
                        super().save(*args, **kwargs)
                        return
                except IntegrityError:
                    self.student_code = ""
            raise RuntimeError("Unable to generate a unique student code after 5 retries")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.student_code


class EducationHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="education_history")
    institution_name = models.CharField(max_length=200)
    level = models.CharField(max_length=100, blank=True)
    course_major = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=100, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    grading_type = models.CharField(max_length=50, blank=True)
    score = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "start_date"]

    def __str__(self) -> str:
        return f"{self.student} - {self.institution_name}"


class StudentAssignedSchool(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="assigned_schools")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="assigned_students")
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="school_assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="school_assignments_made"
    )
    notes = models.TextField(blank=True)
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("student", "school")]
        indexes = [
            models.Index(fields=["student"]),
            models.Index(fields=["school"]),           # INFRA-001: school → students count
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.school}"


class StudentSchoolDocument(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="school_documents")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_documents")
    category = models.CharField(max_length=25, choices=DocumentCategory.choices, db_index=True)
    file_name = models.CharField(max_length=255)
    file_url = models.CharField(max_length=500)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_school_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["student", "school", "category"])]
        ordering = ["category", "uploaded_at"]

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __str__(self) -> str:
        return f"{self.student} / {self.school} / {self.category} / {self.file_name}"


class StudentPreference(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="preferences")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_preferences")
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_preferences"
    )
    preferred_country = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "school", "course"],
                name="unique_student_school_course",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=["student"])]

    def __str__(self) -> str:
        return f"{self.student} → {self.school}"


class StudentActivity(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=50, choices=ActivityType.choices, db_index=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_activities"
    )
    is_pinned = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "created_at"])]

    def __str__(self) -> str:
        return f"{self.student} - {self.activity_type}"


class Enquiry(models.Model):
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=EnquiryStatus.choices, default=EnquiryStatus.OPEN, db_index=True)
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_enquiries"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_enquiries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]

    def clean(self):
        if not self.lead and not self.student:
            raise ValidationError("Enquiry must be linked to either a lead or a student.")

    def __str__(self) -> str:
        return self.subject


class WorkExperience(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="work_experiences")
    company = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "start_date"]

    def __str__(self) -> str:
        return f"{self.student} - {self.company}"


class Reference(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="references")
    name = models.CharField(max_length=200)
    organization = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    relationship = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.student} - {self.name}"


class StudentProfileDocument(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="profile_documents")
    category = models.CharField(max_length=30, choices=ProfileDocumentCategory.choices, db_index=True)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["category", "uploaded_at"]
        indexes = [models.Index(fields=["student", "category"])]

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __str__(self) -> str:
        return f"{self.student} / {self.category} / {self.file_name}"


class PriorityItemDismissal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="priority_dismissals"
    )
    item_type = models.CharField(max_length=20)  # 'document' or 'deadline'
    item_id = models.IntegerField()
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "item_type", "item_id")]

    def __str__(self) -> str:
        return f"{self.user} dismissed {self.item_type}:{self.item_id}"


class FollowUp(models.Model):
    status = models.CharField(max_length=20, choices=FollowUpStatus.choices, default=FollowUpStatus.PENDING, db_index=True)
    scheduled_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name="followups")
    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, null=True, blank=True, related_name="followups")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name="followups")

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_followups"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_followups"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["assigned_to", "status"]),   # INFRA-001: upcoming follow-ups
        ]

    def clean(self):
        linked = [bool(self.lead_id), bool(self.enquiry_id), bool(self.student_id)]
        if sum(linked) != 1:
            raise ValidationError("FollowUp must be linked to exactly one of lead, enquiry, or student.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_done(self):
        self.status = FollowUpStatus.DONE
        self.completed_at = timezone.now()

    def __str__(self) -> str:
        return f"{self.status} @ {self.scheduled_at.isoformat()}"
