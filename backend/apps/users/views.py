from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .throttles import LoginRateThrottle, PasswordResetRateThrottle
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserPublicSerializer,
)

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        from apps.common.email_service import send_welcome_email
        send_welcome_email(user)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (LoginRateThrottle,)

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(ser.validated_data)


class LogoutView(APIView):
    """
    HIGH-001: Blacklist the provided refresh token on logout.

    The client must send the refresh token in the request body.
    The corresponding access token will expire naturally (15 min).
    Both session and JWT logout are handled independently.

    POST /api/auth/logout/
    Body: {"refresh": "<refresh_token>"}
    Returns: 204 No Content
    """

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get("refresh", "")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                # Already blacklisted or invalid — not an error from the client's perspective.
                pass
            except Exception:  # noqa: BLE001
                # Never fail logout due to blacklist errors.
                logger.warning(
                    "Logout: failed to blacklist refresh token for user %s",
                    request.user.pk,
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RefreshView(TokenRefreshView):
    permission_classes = (permissions.AllowAny,)


class MeView(APIView):
    def get(self, request):
        return Response(UserPublicSerializer(request.user).data)

    def patch(self, request):
        ser = ProfileUpdateSerializer(instance=request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(UserPublicSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    """
    Request a password reset email.

    HIGH-002: Rate limited per IP (3/min via throttle) AND per email address
    (max 2 tokens in a 15-minute window) to prevent email spam abuse.
    Account enumeration is prevented — always returns the same 200 response.
    """

    permission_classes = (permissions.AllowAny,)
    throttle_classes = (PasswordResetRateThrottle,)

    # Neutral response that never reveals whether the email exists.
    _NEUTRAL_RESPONSE = {"detail": "If the email exists, a reset link was sent."}

    def post(self, request):
        ser = PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        email = ser.validated_data["email"].lower().strip()

        from .models import PasswordResetToken, User

        user = User.objects.filter(email=email, is_active=True).first()

        if user:
            # HIGH-002: Per-email rate limit — max 2 reset tokens per 15 minutes.
            window_start = timezone.now() - timedelta(minutes=15)
            recent_count = PasswordResetToken.objects.filter(
                user=user,
                created_at__gte=window_start,
            ).count()

            if recent_count >= 2:
                # Silently drop — do not reveal the rate limit to callers.
                logger.warning(
                    "Password reset rate limit hit for user %s", user.pk
                )
                return Response(self._NEUTRAL_RESPONSE)

            token_obj = PasswordResetToken.mint(user=user, ttl_minutes=30)
            try:
                from apps.common.email_service import send_password_reset_email
                reset_link = (
                    f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
                    f"/reset-password.html?token={token_obj.token}"
                )
                send_password_reset_email(user, reset_link)
            except Exception:  # noqa: BLE001
                # Email delivery failure must not block token creation.
                # The token is already persisted; the user can try again.
                logger.warning(
                    "Password reset email could not be sent for user %s", user.pk
                )

        return Response(self._NEUTRAL_RESPONSE)


class PasswordResetConfirmView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)
