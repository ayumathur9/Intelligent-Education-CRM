from __future__ import annotations

from rest_framework import serializers

from .models import Course, Enquiry, FollowUp, Lead, School, Student, StudentActivity, StudentPreference


class SchoolSerializer(serializers.ModelSerializer):
    courses_count = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = (
            "id", "name", "country", "description", "website",
            "is_active", "courses_count", "created_by", "created_at", "updated_at",
        )
        read_only_fields = ("created_by",)

    def get_courses_count(self, obj):
        return obj.courses.filter(is_active=True).count()


class CourseSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Course
        fields = (
            "id", "code", "name", "description", "duration_weeks", "fee_amount",
            "is_active", "school", "school_name", "available_countries", "intake_months",
            "created_at", "updated_at",
        )


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = (
            "id", "full_name", "phone", "email", "source",
            "course_interested", "status", "assigned_to", "notes",
            "created_by", "created_at", "updated_at",
        )
        read_only_fields = ("created_by",)


class StudentSerializer(serializers.ModelSerializer):
    counselor_name = serializers.CharField(source="counselor.full_name", read_only=True)
    counselor_phone = serializers.CharField(source="counselor.phone", read_only=True)
    counselor_email = serializers.EmailField(source="counselor.email", read_only=True)
    poc_name = serializers.CharField(source="poc.full_name", read_only=True)
    poc_phone = serializers.CharField(source="poc.phone", read_only=True)
    poc_email = serializers.EmailField(source="poc.email", read_only=True)

    class Meta:
        model = Student
        fields = (
            # Core identity
            "id", "user", "student_code", "full_name", "phone", "email",
            "course", "joined_on", "is_active", "pack_selected",
            # Assigned team
            "counselor", "counselor_name", "counselor_phone", "counselor_email",
            "poc", "poc_name", "poc_phone", "poc_email",
            # Personal details
            "dob", "gender", "nationality", "country_of_birth", "native_language",
            # Passport
            "passport_name", "passport_number", "passport_issue_location",
            "passport_issue_date", "passport_expiry_date",
            # Permanent address
            "perm_country", "perm_line_1", "perm_line_2", "perm_city", "perm_state", "perm_postcode",
            # Current address
            "curr_same_as_perm", "curr_country", "curr_line_1", "curr_line_2",
            "curr_city", "curr_state", "curr_postcode",
            # Father
            "father_name", "father_phone", "father_email", "father_dob",
            "father_education", "father_profession", "father_company",
            "father_position", "father_annual_income",
            # Mother
            "mother_name", "mother_phone", "mother_email", "mother_dob",
            "mother_education", "mother_profession", "mother_company",
            "mother_position", "mother_annual_income",
            # Emergency contact
            "emergency_name", "emergency_relationship", "emergency_mobile", "emergency_email",
            # Destinations
            "destination_countries",
            # Timestamps
            "created_at", "updated_at",
        )
        read_only_fields = ("student_code", "created_at", "updated_at")


class StudentPreferenceSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_country = serializers.CharField(source="school.country", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = StudentPreference
        fields = (
            "id", "student", "school", "school_name", "school_country",
            "course", "course_name", "preferred_country", "notes",
            "created_at", "updated_at",
        )
        read_only_fields = ("student",)


class StudentActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentActivity
        fields = (
            "id", "student", "activity_type", "description",
            "created_at", "created_by",
        )
        read_only_fields = ("student", "created_by")


class EnquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = Enquiry
        fields = (
            "id", "subject", "message", "status", "lead", "student",
            "assigned_to", "created_by", "created_at", "updated_at",
        )
        read_only_fields = ("created_by",)


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = (
            "id", "status", "scheduled_at", "completed_at", "note",
            "lead", "enquiry", "student", "assigned_to",
            "created_by", "created_at", "updated_at",
        )
        read_only_fields = ("created_by", "completed_at")

    def validate(self, attrs):
        lead = attrs.get("lead") if "lead" in attrs else getattr(self.instance, "lead", None)
        enquiry = attrs.get("enquiry") if "enquiry" in attrs else getattr(self.instance, "enquiry", None)
        student = attrs.get("student") if "student" in attrs else getattr(self.instance, "student", None)
        if sum([bool(lead), bool(enquiry), bool(student)]) != 1:
            raise serializers.ValidationError("FollowUp must be linked to exactly one of lead, enquiry, or student.")
        return attrs
