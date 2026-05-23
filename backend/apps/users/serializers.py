from __future__ import annotations

from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordResetToken, Role, User
from django.utils import timezone


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "role", "date_joined")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)

    class Meta:
        model = User
        fields = ("email", "password", "full_name", "phone", "role")

    def validate_role(self, value: str) -> str:
        # Prevent privilege escalation during open registration.
        request = self.context.get("request")
        if value in (Role.ADMIN, Role.COUNSELOR):
            if not request or not request.user.is_authenticated or request.user.role != Role.ADMIN:
                raise serializers.ValidationError("Only admins can create admin/counselor users.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        ip = self._get_ip(request)
        email = attrs["email"]

        # SEC-002: block locked-out accounts before hitting the DB authenticator.
        try:
            from apps.common.security.anomaly_detection import is_account_locked
            if is_account_locked(email):
                raise serializers.ValidationError(_("Account is temporarily locked. Try again later."))
        except serializers.ValidationError:
            raise
        except Exception:
            pass

        user = authenticate(email=email, password=attrs["password"])
        if not user:
            # SEC-002: record failed login for both IP and per-email counters.
            try:
                from apps.common.security.anomaly_detection import (
                    record_failed_login,
                    record_failed_login_for_email,
                )
                record_failed_login(ip)
                record_failed_login_for_email(email)
            except Exception:
                pass
            raise serializers.ValidationError(_("Invalid credentials."))
        if not user.is_active:
            raise serializers.ValidationError(_("User is inactive."))

        # SEC-002: clear failure counters on successful authentication.
        try:
            from apps.common.security.anomaly_detection import (
                check_impossible_velocity,
                clear_failed_login_attempts,
            )
            check_impossible_velocity(user.pk, ip)
            clear_failed_login_attempts(email)
        except Exception:
            pass

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserPublicSerializer(user).data,
        }

    @staticmethod
    def _get_ip(request) -> str:
        if request is None:
            return "unknown"
        # HIGH-5: Use django-ipware for trusted proxy-aware extraction.
        try:
            from ipware import get_client_ip
            ip, _ = get_client_ip(request)
            return ip or "unknown"
        except ImportError:
            pass
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "unknown")


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("full_name", "phone")


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self) -> PasswordResetToken | None:
        email = self.validated_data["email"].lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            return None
        return PasswordResetToken.mint(user=user, ttl_minutes=30)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=10)

    def validate(self, attrs):
        token = attrs["token"]
        prt = PasswordResetToken.objects.filter(token=token).select_related("user").first()
        if not prt or not prt.is_valid():
            raise serializers.ValidationError("Invalid or expired token.")
        attrs["prt"] = prt
        return attrs

    def save(self):
        prt: PasswordResetToken = self.validated_data["prt"]
        user = prt.user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        prt.used_at = prt.used_at or timezone.now()
        prt.save(update_fields=["used_at"])
        return user

