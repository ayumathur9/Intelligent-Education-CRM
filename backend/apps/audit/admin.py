from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "action", "entity", "entity_id", "created_at")
    search_fields = ("action", "entity", "entity_id", "actor__email")
    list_filter = ("action", "entity")

