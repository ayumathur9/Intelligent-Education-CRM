from __future__ import annotations

from rest_framework import serializers, viewsets, permissions

from apps.users.permissions import IsAdmin
from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = (
            "id", "actor", "actor_email", "action", "entity", "entity_id",
            "metadata", "ip_address", "user_agent", "changes", "created_at",
        )
        read_only_fields = fields

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor else None


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit log endpoint — admin access only.
    Returns all activity log entries ordered by most recent first.
    """
    serializer_class = ActivityLogSerializer
    permission_classes = (permissions.IsAuthenticated, IsAdmin)
    queryset = ActivityLog.objects.select_related("actor").order_by("-created_at")
    filterset_fields = ("action", "entity", "actor")
    search_fields = ("action", "entity", "entity_id", "actor__email")
    ordering_fields = ("created_at", "action")
