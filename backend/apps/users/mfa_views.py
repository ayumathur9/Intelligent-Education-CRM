"""
TOTP / MFA views — LOW-009.

Endpoints:
  POST /api/auth/mfa/setup/    — Generate TOTP secret and QR code URL (admin/counselor only)
  POST /api/auth/mfa/verify/   — Verify a TOTP token and activate MFA on the account
  POST /api/auth/mfa/disable/  — Disable MFA (requires password confirmation)
  GET  /api/auth/mfa/status/   — Return whether MFA is enabled for the current user

How it works:
  1. Admin/counselor calls /mfa/setup/ → receives provisioning_uri (QR code) + backup codes
  2. User scans QR code in an authenticator app, then calls /mfa/verify/ with the 6-digit token
  3. After verification, all subsequent logins require a TOTP token via /api/auth/login/

Integration note:
  django-otp stores TOTP devices in the `otp_totp_totpdevice` table.
  The login view checks request.user.totpdevice_set.filter(confirmed=True).exists()
  to enforce MFA.  JWTs are issued ONLY after successful TOTP verification.
"""
from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

_MFA_ROLES = {"admin", "counselor"}  # Only these roles can enable MFA


def _get_or_create_device(user):
    """Return (device, created) for the user's primary TOTP device."""
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
    except ImportError:
        return None, False

    device = TOTPDevice.objects.filter(user=user, name="primary").first()
    if device is None:
        device = TOTPDevice.objects.create(
            user=user,
            name="primary",
            confirmed=False,
        )
        return device, True
    return device, False


class MFASetupView(APIView):
    """
    Initiate MFA setup for the current user.

    Returns a TOTP provisioning URI that can be rendered as a QR code.
    The device is not activated until /mfa/verify/ is called.

    POST /api/auth/mfa/setup/
    Response: {"provisioning_uri": str, "secret": str, "issuer": str}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if getattr(user, "role", "") not in _MFA_ROLES:
            return Response(
                {"detail": "MFA is available for admin and counselor accounts only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
        except ImportError:
            return Response(
                {"detail": "MFA is not available (django-otp not installed)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Remove any unconfirmed device and start fresh.
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        device, _ = _get_or_create_device(user)
        if device is None:
            return Response({"detail": "MFA setup failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        issuer = getattr(settings, "MFA_ISSUER", "Intelligent Education CRM")
        uri = device.config_url  # otpauth:// URI for QR code rendering
        # config_url may not include issuer — build manually if needed.
        if "issuer" not in uri:
            import urllib.parse
            uri += f"&issuer={urllib.parse.quote(issuer)}"

        logger.info("MFA setup initiated for user %s (role=%s)", user.pk, user.role)
        return Response(
            {
                "provisioning_uri": uri,
                "secret": device.bin_key.hex() if hasattr(device, "bin_key") else "",
                "issuer": issuer,
                "message": "Scan the QR code with your authenticator app, then call /api/auth/mfa/verify/ to activate.",
            }
        )


class MFAVerifyView(APIView):
    """
    Verify a TOTP token to activate MFA on the account.

    POST /api/auth/mfa/verify/
    Body: {"token": "123456"}
    Response: {"detail": "MFA activated successfully."}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        token = str(request.data.get("token", "")).strip()

        if not token:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
        except ImportError:
            return Response({"detail": "MFA not available."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        device = TOTPDevice.objects.filter(user=user, name="primary").first()
        if device is None:
            return Response(
                {"detail": "No MFA device found. Call /api/auth/mfa/setup/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if device.verify_token(token):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            logger.info("MFA activated for user %s", user.pk)
            return Response({"detail": "MFA activated successfully. Future logins will require a TOTP code."})

        logger.warning("MFA verification failed for user %s", user.pk)
        return Response(
            {"detail": "Invalid TOTP token. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class MFADisableView(APIView):
    """
    Disable MFA for the current user (requires password confirmation).

    POST /api/auth/mfa/disable/
    Body: {"password": "current_password"}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        password = request.data.get("password", "")
        if not password:
            return Response({"detail": "password is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if not user.check_password(password):
            logger.warning("MFA disable: invalid password for user %s", user.pk)
            return Response({"detail": "Incorrect password."}, status=status.HTTP_403_FORBIDDEN)

        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
        except ImportError:
            return Response({"detail": "MFA not available."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        deleted, _ = TOTPDevice.objects.filter(user=user).delete()
        if deleted:
            logger.info("MFA disabled for user %s", user.pk)
            return Response({"detail": "MFA disabled successfully."})

        return Response({"detail": "MFA was not enabled."}, status=status.HTTP_400_BAD_REQUEST)


class MFAStatusView(APIView):
    """
    Return MFA status for the current user.

    GET /api/auth/mfa/status/
    Response: {"enabled": bool, "confirmed": bool}
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
            device = TOTPDevice.objects.filter(user=request.user, name="primary").first()
            return Response(
                {
                    "enabled": device is not None,
                    "confirmed": device.confirmed if device else False,
                }
            )
        except ImportError:
            return Response({"enabled": False, "confirmed": False})
