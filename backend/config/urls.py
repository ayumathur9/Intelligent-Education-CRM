from django.conf import settings
from django.contrib import admin
from django.urls import include, path
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

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
