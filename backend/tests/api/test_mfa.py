"""
TOTP / MFA endpoint tests — LOW-009.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


MFA_SETUP_URL = "/api/auth/mfa/setup/"
MFA_VERIFY_URL = "/api/auth/mfa/verify/"
MFA_DISABLE_URL = "/api/auth/mfa/disable/"
MFA_STATUS_URL = "/api/auth/mfa/status/"

# Patch path for TOTPDevice: mfa_views imports it inside function bodies,
# so we patch the underlying module.
_TOTP_PATH = "django_otp.plugins.otp_totp.models.TOTPDevice"


@pytest.fixture
def mock_device():
    """A pre-configured mock TOTPDevice."""
    d = MagicMock()
    d.confirmed = False
    d.config_url = "otpauth://totp/CRM:user@test.com?secret=JBSWY3DPEHPK3PXP&issuer=CRM"
    d.bin_key = b"\x90\xce\xb6\xbc\xde\x78\xf0\x12"
    d.verify_token.return_value = True
    return d


class TestMFAStatus:
    def test_unauthenticated_returns_401(self, api_client):
        resp = api_client.get(MFA_STATUS_URL)
        assert resp.status_code == 401

    def test_admin_can_check_status_no_device(self, admin_client):
        """MFA status returns enabled=False when no device exists."""
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.first.return_value = None
            resp = admin_client.get(MFA_STATUS_URL)
        assert resp.status_code == 200
        assert resp.data["enabled"] is False
        assert resp.data["confirmed"] is False

    def test_admin_can_check_status_with_confirmed_device(self, admin_client, mock_device):
        mock_device.confirmed = True
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.first.return_value = mock_device
            resp = admin_client.get(MFA_STATUS_URL)
        assert resp.status_code == 200
        assert resp.data["enabled"] is True
        assert resp.data["confirmed"] is True


class TestMFASetup:
    def test_student_cannot_setup_mfa(self, student_client):
        resp = student_client.post(MFA_SETUP_URL)
        assert resp.status_code == 403
        detail = resp.data["detail"].lower()
        assert "admin" in detail or "counselor" in detail

    def test_editor_cannot_setup_mfa(self, editor_client):
        resp = editor_client.post(MFA_SETUP_URL)
        assert resp.status_code == 403

    def test_admin_can_initiate_setup(self, admin_client, mock_device):
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.delete.return_value = (0, {})
            MockDevice.objects.filter.return_value.first.return_value = None
            MockDevice.objects.create.return_value = mock_device
            resp = admin_client.post(MFA_SETUP_URL)

        assert resp.status_code == 200
        assert "provisioning_uri" in resp.data
        assert "otpauth://" in resp.data["provisioning_uri"]

    def test_counselor_can_initiate_setup(self, counselor_client, mock_device):
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.delete.return_value = (0, {})
            MockDevice.objects.filter.return_value.first.return_value = None
            MockDevice.objects.create.return_value = mock_device
            resp = counselor_client.post(MFA_SETUP_URL)
        assert resp.status_code == 200


class TestMFAVerify:
    def test_verify_without_device_returns_400(self, admin_client):
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.first.return_value = None
            resp = admin_client.post(MFA_VERIFY_URL, {"token": "123456"}, format="json")
        assert resp.status_code == 400
        assert "setup" in resp.data["detail"].lower()

    def test_missing_token_returns_400(self, admin_client):
        resp = admin_client.post(MFA_VERIFY_URL, {}, format="json")
        assert resp.status_code == 400
        assert "token" in resp.data["detail"].lower()

    def test_valid_token_activates_mfa(self, admin_client, mock_device):
        mock_device.verify_token.return_value = True
        mock_device.confirmed = False
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.first.return_value = mock_device
            resp = admin_client.post(MFA_VERIFY_URL, {"token": "123456"}, format="json")
        assert resp.status_code == 200
        assert "activated" in resp.data["detail"].lower()
        mock_device.save.assert_called_once()

    def test_invalid_token_returns_400(self, admin_client, mock_device):
        mock_device.verify_token.return_value = False
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.first.return_value = mock_device
            resp = admin_client.post(MFA_VERIFY_URL, {"token": "000000"}, format="json")
        assert resp.status_code == 400
        assert "invalid" in resp.data["detail"].lower()


class TestMFADisable:
    def test_missing_password_returns_400(self, admin_client):
        resp = admin_client.post(MFA_DISABLE_URL, {}, format="json")
        assert resp.status_code == 400

    def test_wrong_password_returns_403(self, admin_client):
        resp = admin_client.post(MFA_DISABLE_URL, {"password": "WrongPassword!"}, format="json")
        assert resp.status_code == 403
        assert "incorrect" in resp.data["detail"].lower()

    def test_correct_password_disables_mfa(self, admin_client):
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.delete.return_value = (1, {})
            resp = admin_client.post(MFA_DISABLE_URL, {"password": "AdminPass123!"}, format="json")
        assert resp.status_code == 200
        assert "disabled" in resp.data["detail"].lower()

    def test_no_device_returns_400(self, admin_client):
        with patch(_TOTP_PATH) as MockDevice:
            MockDevice.objects.filter.return_value.delete.return_value = (0, {})
            resp = admin_client.post(MFA_DISABLE_URL, {"password": "AdminPass123!"}, format="json")
        assert resp.status_code == 400
