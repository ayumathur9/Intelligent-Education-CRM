from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "read_at", "created_at")
    search_fields = ("user__email", "title")
    list_filter = ("read_at",)

