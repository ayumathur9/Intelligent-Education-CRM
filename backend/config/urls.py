from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as _media_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser

# In production, only Django admins can reach the schema/docs endpoints.
_docs_perms = [] if settings.DEBUG else [IsAdminUser]

urlpatterns = [
    # Frontend (session-auth HTML pages)
    path("", include("apps.frontend.urls")),
    # Django built-in admin
    path("admin/", admin.site.urls),
    # REST API (JWT-auth)
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=_docs_perms), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=_docs_perms), name="swagger-ui"),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.crm.urls")),
    path("api/", include("apps.files.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.notifications.urls")),
]

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", _media_serve, {"document_root": settings.MEDIA_ROOT}),
]
