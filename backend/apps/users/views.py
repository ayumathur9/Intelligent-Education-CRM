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

from .throttles import LoginRateThrottle, PasswordResetRateThrottle, RegisterRateThrottle
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
    throttle_classes = (RegisterRateThrottle,)
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        from django.conf import settings as _s
        user = serializer.save()

        # HIGH-2: Send email verification link when EMAIL_VERIFICATION_REQUIRED is on.
        if getattr(_s, "EMAIL_VERIFICATION_REQUIRED", False):
            self._send_verification_email(user)
        else:
            # Internal deployment — send welcome email and mark as verified.
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])
            try:
                from apps.users.tasks import send_welcome_email_task
                send_welcome_email_task.delay(user.pk)
            except Exception:
                from apps.common.email_service import send_welcome_email
                send_welcome_email(user)

    @staticmethod
    def _send_verification_email(user) -> None:
        import hashlib
        import hmac
        import time
        from django.conf import settings as _s
        # Include a 48-hour expiry window in the signed payload.
        # The timestamp is the number of complete 48-hour periods since epoch,
        # so the token is valid for up to 48 hours after generation.
        window = int(time.time()) // (48 * 3600)
        token = hmac.new(
            _s.SECRET_KEY.encode(),
            f"{user.pk}:{user.email}:{window}".encode(),
            hashlib.sha256,
        ).hexdigest()
        verify_url = (
            f"{_s.FRONTEND_BASE_URL.rstrip('/')}"
            f"/api/auth/verify-email/?uid={user.pk}&token={token}"
        )
        try:
            from apps.common.email_service import _send
            _send(
                subject="Verify your Intelligent Education email",
                text_body=(
                    f"Hi {user.full_name or user.email},\n\n"
                    f"Click to verify your email:\n{verify_url}\n\n"
                    "If you did not register, ignore this email."
                ),
                html_body=(
                    f"<p>Hi {user.full_name or user.email},</p>"
                    f'<p><a href="{verify_url}">Verify your email</a></p>'
                ),
                to=[user.email],
            )
        except Exception:
            logger.warning("Could not send verification email to %s", user.email)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (LoginRateThrottle,)

    def post(self, request):
        # Pass request so the serializer can perform SEC-002 anomaly checks.
        ser = LoginSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        return Response(ser.validated_data)


class LogoutView(APIView):
    """
    HIGH-001: Blacklist the provided refresh token on logout.

    LOW: Restricted to POST only — GET requests cannot trigger logout
    (prevents CSRF-style logout via image tags or link prefetch).

    The client must send the refresh token in the request body.
    The corresponding access token will expire naturally (15 min).
    Both session and JWT logout are handled independently.

    POST /api/auth/logout/
    Body: {"refresh": "<refresh_token>"}
    Returns: 204 No Content
    """

    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ["post", "options"]

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
            reset_link = (
                f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
                f"/reset-password.html?token={token_obj.token}"
            )
            try:
                from apps.users.tasks import send_password_reset_email_task
                send_password_reset_email_task.delay(user.pk, reset_link)
            except Exception:  # noqa: BLE001
                # Celery unavailable — fall back to synchronous email.
                try:
                    from apps.common.email_service import send_password_reset_email
                    send_password_reset_email(user, reset_link)
                except Exception:
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


class EmailVerifyView(APIView):
    """
    HIGH-2: Verify a user's email address via signed token.

    GET /api/auth/verify-email/?uid=<pk>&token=<hmac>
    Returns 200 on success, 400 if the token is invalid or already verified.
    """

    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        import hashlib
        import hmac
        import time
        from django.conf import settings as _s
        from .models import User

        uid = request.query_params.get("uid", "")
        token = request.query_params.get("token", "")

        try:
            user = User.objects.get(pk=int(uid))
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Invalid verification link."}, status=status.HTTP_400_BAD_REQUEST)

        # Accept the current 48-hour window or the immediately preceding one
        # to handle links generated just before a window boundary.
        current_window = int(time.time()) // (48 * 3600)
        valid = False
        for window in (current_window, current_window - 1):
            expected = hmac.new(
                _s.SECRET_KEY.encode(),
                f"{user.pk}:{user.email}:{window}".encode(),
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(token, expected):
                valid = True
                break

        if not valid:
            logger.warning("EmailVerifyView: invalid or expired token for user %s", uid)
            return Response({"detail": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)

        if user.is_email_verified:
            return Response({"detail": "Email already verified."})

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        logger.info("EmailVerifyView: email verified for user %s", user.pk)
        return Response({"detail": "Email verified successfully."})


class InviteCreateView(APIView):
    """
    Admin-only: generate a staff invite token and send the invite email.

    POST /api/auth/invite/
    Body: {"email": "...", "role": "counselor|editor|admin"}
    Returns: {"detail": "Invite sent.", "invite_id": <id>}
    """

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        from .models import StaffInvite, Role

        if request.user.role != Role.ADMIN:
            return Response({"detail": "Only admins can send invites."}, status=status.HTTP_403_FORBIDDEN)

        email = (request.data.get("email") or "").strip().lower()
        role = (request.data.get("role") or "").strip().lower()

        if not email:
            return Response({"detail": "email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if role not in (Role.ADMIN, Role.COUNSELOR, Role.EDITOR, Role.STUDENT):
            return Response({"detail": "role must be admin, counselor, editor, or student."}, status=status.HTTP_400_BAD_REQUEST)

        # Invalidate any pending invite for the same email+role.
        StaffInvite.objects.filter(email=email, role=role, accepted_at__isnull=True).delete()

        invite = StaffInvite.mint(email=email, role=role, invited_by=request.user)

        try:
            from apps.users.tasks import send_staff_invite_email_task
            send_staff_invite_email_task.delay(invite.pk)
        except Exception:
            from apps.common.email_service import send_staff_invite_email
            send_staff_invite_email(invite)

        logger.info("Invite created by %s for %s (%s)", request.user.pk, email, role)
        return Response({"detail": "Invite sent.", "invite_id": invite.pk}, status=status.HTTP_201_CREATED)


class InviteAcceptView(APIView):
    """
    Accept a staff invite and register the account.

    POST /api/auth/invite/accept/
    Body: {"token": "...", "full_name": "...", "password": "..."}
    """

    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        from .models import StaffInvite, User
        from django.utils import timezone as tz

        token = (request.data.get("token") or "").strip()
        full_name = (request.data.get("full_name") or "").strip()
        password = request.data.get("password") or ""

        if not token:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 8:
            return Response({"detail": "Password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invite = StaffInvite.objects.select_for_update().get(token=token)
        except StaffInvite.DoesNotExist:
            return Response({"detail": "Invalid invite link."}, status=status.HTTP_400_BAD_REQUEST)

        if not invite.is_valid():
            return Response({"detail": "This invite has expired or already been used."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=invite.email).exists():
            return Response({"detail": "An account for this email already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=invite.email,
            password=password,
            full_name=full_name,
            role=invite.role,
            is_email_verified=True,
        )

        invite.accepted_at = tz.now()
        invite.save(update_fields=["accepted_at"])

        # Send role-appropriate onboarding email.
        try:
            from apps.users.tasks import send_staff_onboarding_email_task
            send_staff_onboarding_email_task.delay(user.pk)
        except Exception:
            from apps.common.email_service import send_staff_onboarding_email
            send_staff_onboarding_email(user)

        logger.info("InviteAcceptView: user %s created via invite %s", user.pk, invite.pk)
        return Response({"detail": "Account created. You can now log in."}, status=status.HTTP_201_CREATED)


class BroadcastEmailView(APIView):
    """
    Admin-only: send a broadcast email (maintenance/incident/restored/general)
    to all users or a specified audience.

    POST /api/admin/broadcast-email/
    Body:
      {
        "broadcast_type": "maintenance|incident|restored|general",
        "body_message": "...",
        "audience": "all|staff|students|admins",   (optional, default: all)
        "custom_subject": "...",                    (optional)
        "meta_fields": {"Downtime window": "...", "ETA": "..."}  (optional)
      }
    """

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        from .models import Role, User

        if request.user.role != Role.ADMIN:
            return Response({"detail": "Only admins can send broadcast emails."}, status=status.HTTP_403_FORBIDDEN)

        broadcast_type = (request.data.get("broadcast_type") or "general").strip().lower()
        body_message = (request.data.get("body_message") or "").strip()
        audience = (request.data.get("audience") or "all").strip().lower()
        custom_subject = (request.data.get("custom_subject") or "").strip()
        meta_fields = request.data.get("meta_fields") or {}

        valid_types = {"maintenance", "incident", "restored", "general"}
        if broadcast_type not in valid_types:
            return Response({"detail": f"broadcast_type must be one of: {', '.join(valid_types)}"}, status=status.HTTP_400_BAD_REQUEST)
        if not body_message:
            return Response({"detail": "body_message is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Build recipient list based on audience
        qs = User.objects.filter(is_active=True).exclude(email="")
        if audience == "staff":
            qs = qs.filter(role__in=[Role.ADMIN, Role.COUNSELOR, Role.EDITOR])
        elif audience == "students":
            qs = qs.filter(role=Role.STUDENT)
        elif audience == "admins":
            qs = qs.filter(role=Role.ADMIN)

        recipients = list(qs.values_list("email", flat=True))
        if not recipients:
            return Response({"detail": "No recipients found for the selected audience."}, status=status.HTTP_400_BAD_REQUEST)

        sent_by = request.user.full_name or request.user.email

        try:
            from apps.common.email_service import send_broadcast_email
            send_broadcast_email(
                broadcast_type=broadcast_type,
                body_message=body_message,
                recipients=recipients,
                sent_by=sent_by,
                meta_fields=meta_fields if isinstance(meta_fields, dict) else {},
                custom_subject=custom_subject,
            )
        except Exception as exc:
            logger.error("BroadcastEmailView: failed — %s", exc)
            return Response({"detail": "Failed to send broadcast email. Check server logs."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(
            "BroadcastEmailView: %s sent '%s' broadcast to %d recipients (audience=%s)",
            request.user.pk, broadcast_type, len(recipients), audience,
        )
        return Response({
            "detail": f"Broadcast sent to {len(recipients)} recipient(s).",
            "recipients_count": len(recipients),
        })
