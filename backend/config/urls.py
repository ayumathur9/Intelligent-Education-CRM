from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser

from apps.common.health import health_check
from apps.common.views import media_proxy

# HIGH-1: Replace the default Django admin site with one that requires
# OTP verification (django-otp OTPAdminSite).  Staff users who have not
# enrolled a TOTP device are redirected to enrol before they can log in.
try:
    from django_otp.admin import OTPAdminSite as _OTPAdminSite
    admin.site.__class__ = _OTPAdminSite
except ImportError:
    pass  # django-otp not installed — falls back to default admin (dev only)

# In production, only Django admins can reach the schema/docs endpoints.
_docs_perms = [] if settings.DEBUG else [IsAdminUser]

urlpatterns = [
    # Infrastructure — HIGH-006: health probe (no auth required)
    path("api/health/", health_check, name="health-check"),
    # Frontend (session-auth HTML pages)
    path("", include("apps.frontend.urls")),
    # Django built-in admin — HIGH-1: requires OTP verification
    path("admin/", admin.site.urls),
    # REST API (JWT-auth)
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=_docs_perms), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=_docs_perms), name="swagger-ui"),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.crm.urls")),
    path("api/", include("apps.files.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.notifications.urls")),
    # CRIT-1: Authenticated media proxy — replaces unauthenticated static serve.
    # In production behind Nginx, set NGINX_MEDIA_ACCEL=1 and add an internal
    # /protected-media/ location that maps to MEDIA_ROOT.
    re_path(r"^media/(?P<path>.+)$", media_proxy, name="media-proxy"),
]
