"""
Tests for SEC-003 MFARequiredForAdmin permission class.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.django_db


def _make_request(user, mfa_token: str = ""):
    req = MagicMock()
    req.user = user
    req.headers = {"X-MFA-Token": mfa_token} if mfa_token else {}
    return req


class TestMFARequiredForAdmin:
    def test_non_admin_passes_without_mfa(self, counselor_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(counselor_user)
        assert perm.has_permission(req, None) is True

    def test_admin_without_enrolled_mfa_passes(self, admin_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(admin_user)
        with patch.object(
            type(admin_user),
            "totpdevice_set",
            new_callable=lambda: property(lambda self: _no_device_qs()),
            create=True,
        ):
            pass
        # Simulate no devices via patching the queryset result.
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exists.return_value = False
        with patch.object(admin_user.__class__, "totpdevice_set", mock_qs, create=True):
            result = perm.has_permission(req, None)
        assert result is True

    def test_admin_with_mfa_no_token_header_denied(self, admin_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(admin_user, mfa_token="")
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exists.return_value = True
        with patch.object(admin_user.__class__, "totpdevice_set", mock_qs, create=True):
            result = perm.has_permission(req, None)
        assert result is False

    def test_admin_with_mfa_invalid_token_denied(self, admin_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(admin_user, mfa_token="000000")
        mock_device = MagicMock()
        mock_device.verify_token.return_value = False
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exists.return_value = True
        mock_qs.filter.return_value.first.return_value = mock_device
        with patch.object(admin_user.__class__, "totpdevice_set", mock_qs, create=True):
            result = perm.has_permission(req, None)
        assert result is False

    def test_admin_with_valid_mfa_token_allowed(self, admin_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(admin_user, mfa_token="123456")
        mock_device = MagicMock()
        mock_device.verify_token.return_value = True
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exists.return_value = True
        mock_qs.filter.return_value.first.return_value = mock_device
        with patch.object(admin_user.__class__, "totpdevice_set", mock_qs, create=True):
            result = perm.has_permission(req, None)
        assert result is True

    def test_unauthenticated_denied(self):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = MagicMock()
        req.user = None
        assert perm.has_permission(req, None) is False

    def test_student_passes_permission(self, student_user):
        from apps.users.permissions import MFARequiredForAdmin
        perm = MFARequiredForAdmin()
        req = _make_request(student_user)
        assert perm.has_permission(req, None) is True


def _no_device_qs():
    """Helper that creates a queryset-like mock returning no devices."""
    m = MagicMock()
    m.filter.return_value.exists.return_value = False
    return m
