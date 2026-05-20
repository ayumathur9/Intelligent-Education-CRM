from rest_framework.routers import DefaultRouter
from .views import ActivityLogViewSet

router = DefaultRouter()
router.register("audit/activity-logs", ActivityLogViewSet, basename="activity-log")

urlpatterns = router.urls
