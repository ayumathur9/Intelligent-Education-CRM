from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.list_notifications, name="notifications-list"),
    path("notifications/read-all/", views.mark_all_read, name="notifications-read-all"),
    path("notifications/<int:pk>/read/", views.mark_read, name="notification-read"),
]
