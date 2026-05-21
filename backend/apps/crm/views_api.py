from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.users.models import Role
from apps.users.permissions import IsCounselorOrAdmin

from .models import Course, Enquiry, FollowUp, Lead, School, Student, StudentActivity, StudentPreference
from .serializers import (
    CourseSerializer,
    EnquirySerializer,
    FollowUpSerializer,
    LeadSerializer,
    SchoolSerializer,
    StudentActivitySerializer,
    StudentPreferenceSerializer,
    StudentSerializer,
)


class SchoolViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    search_fields = ("name", "country", "description")
    ordering_fields = ("name", "country", "created_at")
    filterset_fields = ("is_active", "country")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsCounselorOrAdmin()]

    def get_queryset(self):
        qs = School.objects.prefetch_related("courses").order_by("country", "name")
        if self.request.user.role == Role.STUDENT:
            return qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    search_fields = ("code", "name")
    ordering_fields = ("created_at", "name", "code")
    filterset_fields = ("is_active", "school")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsCounselorOrAdmin()]

    def get_queryset(self):
        qs = Course.objects.select_related("school").order_by("-created_at")
        if self.request.user.role == Role.STUDENT:
            return qs.filter(is_active=True)
        return qs


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.select_related("course_interested", "assigned_to", "created_by").order_by("-created_at")
    serializer_class = LeadSerializer
    permission_classes = (IsCounselorOrAdmin,)
    search_fields = ("full_name", "phone", "email", "source", "notes")
    ordering_fields = ("created_at", "updated_at", "status", "full_name")
    filterset_fields = ("status", "assigned_to", "course_interested")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class StudentViewSet(viewsets.ModelViewSet):
    """
    Student CRUD viewset.

    LOW-002: Supports cursor-based pagination via ``?cursor=<token>`` for stable
    traversal of large student lists.  Page-number pagination remains available
    via the standard ``?page=`` parameter (default when no cursor is provided).
    """

    serializer_class = StudentSerializer
    search_fields = ("student_code", "full_name", "phone", "email")
    ordering_fields = ("created_at", "updated_at", "student_code", "full_name")
    filterset_fields = ("is_active", "course")

    def get_permissions(self):
        if self.action in ("list", "retrieve", "update", "partial_update", "destroy", "create"):
            return [IsCounselorOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return Student.objects.select_related("course", "user", "counselor", "poc").order_by("-created_at")

    def get_pagination_class(self):
        # LOW-002: activate cursor pagination when ?cursor param is present.
        if "cursor" in self.request.query_params:
            from apps.common.pagination import CursorResultsSetPagination
            return CursorResultsSetPagination
        return None  # use DRF default (StandardResultsSetPagination from settings)

    def paginate_queryset(self, queryset):
        paginator_class = self.get_pagination_class()
        if paginator_class is not None:
            self.pagination_class = paginator_class
        return super().paginate_queryset(queryset)

    @action(detail=False, methods=["get", "patch"], url_path="me", permission_classes=(permissions.IsAuthenticated,))
    def me(self, request):
        if request.user.role != Role.STUDENT:
            return Response({"detail": "Only student users can access this endpoint."}, status=403)
        student = Student.objects.select_related("counselor", "poc", "course").filter(user=request.user).first()
        if not student:
            return Response({"detail": "Student profile not found."}, status=404)
        if request.method.lower() == "get":
            return Response(self.get_serializer(student).data)
        ser = self.get_serializer(instance=student, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(self.get_serializer(student).data)


class StudentPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = StudentPreferenceSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.STUDENT:
            student = Student.objects.filter(user=user).first()
            if not student:
                return StudentPreference.objects.none()
            return StudentPreference.objects.select_related("school", "course").filter(student=student)
        return StudentPreference.objects.select_related("school", "course", "student").all()

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == Role.STUDENT:
            student = Student.objects.filter(user=user).first()
            if not student:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("Student profile not found for this user.")
            serializer.save(student=student)
            StudentActivity.objects.create(
                student=student,
                activity_type="preference_saved",
                description=f"Saved preference for {serializer.instance.school.name}",
                created_by=user,
            )
        else:
            serializer.save()


class StudentActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StudentActivitySerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.STUDENT:
            student = Student.objects.filter(user=user).first()
            if not student:
                return StudentActivity.objects.none()
            return StudentActivity.objects.filter(student=student).order_by("-created_at")
        return StudentActivity.objects.select_related("student").order_by("-created_at")


class EnquiryViewSet(viewsets.ModelViewSet):
    queryset = Enquiry.objects.select_related("lead", "student", "assigned_to", "created_by").order_by("-created_at")
    serializer_class = EnquirySerializer
    permission_classes = (IsCounselorOrAdmin,)
    search_fields = ("subject", "message")
    ordering_fields = ("created_at", "updated_at", "status")
    filterset_fields = ("status", "assigned_to", "lead", "student")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class FollowUpViewSet(viewsets.ModelViewSet):
    queryset = FollowUp.objects.select_related(
        "lead", "enquiry", "student", "assigned_to", "created_by"
    ).order_by("-scheduled_at")
    serializer_class = FollowUpSerializer
    permission_classes = (IsCounselorOrAdmin,)
    search_fields = ("note",)
    ordering_fields = ("scheduled_at", "created_at", "status")
    filterset_fields = ("status", "assigned_to", "lead", "enquiry", "student")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_done(self, request, pk=None):
        followup: FollowUp = self.get_object()
        followup.mark_done()
        followup.save(update_fields=["status", "completed_at"])
        return Response(self.get_serializer(followup).data)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = (IsCounselorOrAdmin,)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        today = timezone.localdate()
        last_30 = timezone.now() - timedelta(days=30)

        lead_by_status = dict(Lead.objects.values("status").annotate(c=Count("id")).values_list("status", "c"))
        enquiry_by_status = dict(Enquiry.objects.values("status").annotate(c=Count("id")).values_list("status", "c"))
        followups_due = FollowUp.objects.filter(status="pending", scheduled_at__date__lte=today).count()
        followups_next_7 = FollowUp.objects.filter(
            status="pending",
            scheduled_at__date__gt=today,
            scheduled_at__date__lte=today + timedelta(days=7),
        ).count()

        return Response(
            {
                "leads": {
                    "total": Lead.objects.count(),
                    "created_last_30_days": Lead.objects.filter(created_at__gte=last_30).count(),
                    "by_status": lead_by_status,
                },
                "students": {"total": Student.objects.count(), "active": Student.objects.filter(is_active=True).count()},
                "courses": {"total": Course.objects.count(), "active": Course.objects.filter(is_active=True).count()},
                "schools": {"total": School.objects.count(), "active": School.objects.filter(is_active=True).count()},
                "enquiries": {"total": Enquiry.objects.count(), "by_status": enquiry_by_status},
                "followups": {"due_or_overdue": followups_due, "next_7_days": followups_next_7},
            }
        )
