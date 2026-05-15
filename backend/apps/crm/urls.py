from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_api import (
    CourseViewSet,
    DashboardViewSet,
    EnquiryViewSet,
    FollowUpViewSet,
    LeadViewSet,
    SchoolViewSet,
    StudentActivityViewSet,
    StudentPreferenceViewSet,
    StudentViewSet,
)

router = DefaultRouter()
router.register(r"crm/schools", SchoolViewSet, basename="crm-schools")
router.register(r"crm/courses", CourseViewSet, basename="crm-courses")
router.register(r"crm/leads", LeadViewSet, basename="crm-leads")
router.register(r"crm/students", StudentViewSet, basename="crm-students")
router.register(r"crm/student-preferences", StudentPreferenceViewSet, basename="crm-student-preferences")
router.register(r"crm/student-activities", StudentActivityViewSet, basename="crm-student-activities")
router.register(r"crm/enquiries", EnquiryViewSet, basename="crm-enquiries")
router.register(r"crm/followups", FollowUpViewSet, basename="crm-followups")
router.register(r"dashboard", DashboardViewSet, basename="dashboard")

urlpatterns = [
    path("", include(router.urls)),
]
