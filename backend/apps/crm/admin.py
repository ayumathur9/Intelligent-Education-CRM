from django.contrib import admin

from .models import (
    Course, EducationHistory, Enquiry, FollowUp, Lead,
    Reference, School, Student, StudentActivity, StudentAssignedSchool,
    StudentPreference, StudentProfileDocument, StudentSchoolDocument,
    WorkExperience,
)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "is_active", "created_at")
    search_fields = ("name", "country", "description")
    list_filter = ("is_active", "country")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "school", "is_active", "duration_weeks", "fee_amount", "created_at")
    search_fields = ("code", "name")
    list_filter = ("is_active", "school")
    raw_id_fields = ("school",)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "status", "source", "assigned_to", "created_at")
    search_fields = ("full_name", "phone", "email", "notes")
    list_filter = ("status", "source")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_code", "full_name", "course", "counselor", "poc", "is_active", "joined_on")
    search_fields = ("student_code", "full_name", "phone", "email")
    list_filter = ("is_active", "course")
    raw_id_fields = ("counselor", "poc", "user")
    fieldsets = (
        ("Basic Info", {"fields": ("user", "student_code", "full_name", "phone", "email", "course", "joined_on", "is_active", "counselor", "poc")}),
        ("Personal Details", {"fields": ("dob", "gender", "nationality", "country_of_birth", "native_language"), "classes": ("collapse",)}),
        ("Passport", {"fields": ("passport_name", "passport_number", "passport_issue_location", "passport_issue_date", "passport_expiry_date"), "classes": ("collapse",)}),
        ("Permanent Address", {"fields": ("perm_country", "perm_line_1", "perm_line_2", "perm_city", "perm_state", "perm_postcode"), "classes": ("collapse",)}),
        ("Current Address", {"fields": ("curr_same_as_perm", "curr_country", "curr_line_1", "curr_line_2", "curr_city", "curr_state", "curr_postcode"), "classes": ("collapse",)}),
        ("Father Details", {"fields": ("father_name", "father_phone", "father_email", "father_dob", "father_education", "father_profession", "father_company", "father_position", "father_annual_income"), "classes": ("collapse",)}),
        ("Mother Details", {"fields": ("mother_name", "mother_phone", "mother_email", "mother_dob", "mother_education", "mother_profession", "mother_company", "mother_position", "mother_annual_income"), "classes": ("collapse",)}),
        ("Emergency Contact", {"fields": ("emergency_name", "emergency_relationship", "emergency_mobile", "emergency_email"), "classes": ("collapse",)}),
        ("Legacy Work & Referee", {"fields": ("destination_countries", "work_company", "work_role", "work_start", "work_end", "work_current", "referee_name", "referee_org", "referee_phone", "referee_email", "referee_relationship"), "classes": ("collapse",)}),
    )


@admin.register(EducationHistory)
class EducationHistoryAdmin(admin.ModelAdmin):
    list_display = ("student", "institution_name", "level", "country", "start_date", "end_date")
    search_fields = ("student__full_name", "institution_name")
    raw_id_fields = ("student",)


@admin.register(StudentAssignedSchool)
class StudentAssignedSchoolAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "course", "assigned_by", "created_at")
    search_fields = ("student__full_name", "school__name")
    list_filter = ("school__country",)
    raw_id_fields = ("student", "school", "course", "assigned_by")


@admin.register(StudentSchoolDocument)
class StudentSchoolDocumentAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "category", "file_name", "uploaded_by", "uploaded_at")
    search_fields = ("student__full_name", "school__name", "file_name")
    list_filter = ("category",)
    raw_id_fields = ("student", "school", "uploaded_by")


@admin.register(StudentPreference)
class StudentPreferenceAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "course", "preferred_country", "created_at")
    search_fields = ("student__full_name", "school__name")
    list_filter = ("school__country", "preferred_country")
    raw_id_fields = ("student", "school", "course")


@admin.register(StudentActivity)
class StudentActivityAdmin(admin.ModelAdmin):
    list_display = ("student", "activity_type", "description", "created_at", "created_by")
    search_fields = ("student__full_name", "description")
    list_filter = ("activity_type",)
    raw_id_fields = ("student",)


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("subject", "status", "lead", "student", "assigned_to", "created_at")
    search_fields = ("subject", "message")
    list_filter = ("status",)


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ("student", "company", "role", "start_date", "end_date", "is_current")
    search_fields = ("student__full_name", "company", "role")
    raw_id_fields = ("student",)


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("student", "name", "organization", "phone", "email", "relationship")
    search_fields = ("student__full_name", "name", "organization")
    raw_id_fields = ("student",)


@admin.register(StudentProfileDocument)
class StudentProfileDocumentAdmin(admin.ModelAdmin):
    list_display = ("student", "category", "file_name", "uploaded_at")
    search_fields = ("student__full_name", "file_name")
    list_filter = ("category",)
    raw_id_fields = ("student",)


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("status", "scheduled_at", "lead", "enquiry", "student", "assigned_to")
    list_filter = ("status",)
    search_fields = ("note",)
