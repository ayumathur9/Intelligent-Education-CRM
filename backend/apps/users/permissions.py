import logging

from rest_framework.permissions import BasePermission

from .models import Role

logger = logging.getLogger(__name__)


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


class MFARequiredForAdmin(BasePermission):
    """
    SEC-003: Require MFA token header for admin users on sensitive endpoints.

    Admins with a confirmed TOTP device must present X-MFA-Token header.
    Non-admin users and unenrolled admins pass through.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.role != Role.ADMIN:
            return True

        try:
            has_mfa = user.totpdevice_set.filter(confirmed=True).exists()
        except Exception:
            return True  # django-otp not installed

        if not has_mfa:
            return True  # Not yet enrolled — pass through

        mfa_token = request.headers.get("X-MFA-Token", "").strip()
        if not mfa_token:
            self.message = "MFA token required (X-MFA-Token header)."
            logger.warning("SEC-003: admin %s accessed endpoint without MFA token", user.pk)
            return False

        device = user.totpdevice_set.filter(confirmed=True).first()
        if not device or not device.verify_token(mfa_token):
            self.message = "Invalid or expired MFA token."
            logger.warning("SEC-003: admin %s provided invalid MFA token", user.pk)
            return False

        return True

