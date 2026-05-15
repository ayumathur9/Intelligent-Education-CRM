from rest_framework.permissions import BasePermission

from .models import Role


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.ADMIN)


class IsCounselorOrAdmin(BasePermission):
    """Counselors and admins only. Does NOT include editors."""
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.COUNSELOR)
        )


class IsEditorOrAdmin(BasePermission):
    """Editors and admins — for document/application management endpoints."""
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.EDITOR)
        )


class IsCounselorEditorOrAdmin(BasePermission):
    """All internal (non-student) roles: admin, counselor, and editor."""
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (Role.ADMIN, Role.COUNSELOR, Role.EDITOR)
        )

