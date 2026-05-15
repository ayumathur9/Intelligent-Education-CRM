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
        user = authenticate(email=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError(_("Invalid credentials."))
        if not user.is_active:
            raise serializers.ValidationError(_("User is inactive."))
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserPublicSerializer(user).data,
        }


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

