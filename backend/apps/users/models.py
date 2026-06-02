from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# LOW-004: E.164-compatible phone validator.
# Accepts optional leading +, then 6–15 digits (ITU-T E.164 max = 15 digits).
_phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{6,15}$",
    message="Enter a valid phone number (6–15 digits, optional leading +).",
)


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    COUNSELOR = "counselor", "Counselor"
    EDITOR = "editor", "Editor"
    STUDENT = "student", "Student"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", Role.STUDENT)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=200, blank=True)
    # LOW-004: E.164 phone validation — blank is allowed (optional field).
    phone = models.CharField(max_length=32, blank=True, validators=[_phone_validator])
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True)
    avatar = models.CharField(max_length=500, blank=True)

    # HIGH-2: Email verification flag. Set to True after the user clicks the
    # verification link. Controlled by EMAIL_VERIFICATION_REQUIRED in settings.
    is_email_verified = models.BooleanField(default=False)

    tutorial_seen = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class StaffInvite(models.Model):
    """Admin-generated invite token for counselors, editors, and admins."""
    email = models.EmailField(db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.COUNSELOR)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sent_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["email", "expires_at"])]

    @classmethod
    def mint(cls, email: str, role: str, invited_by, ttl_hours: int = 72) -> "StaffInvite":
        return cls.objects.create(
            email=email,
            role=role,
            token=secrets.token_urlsafe(32),
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )

    def is_valid(self) -> bool:
        return self.accepted_at is None and self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"Invite<{self.email} / {self.role}>"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "expires_at"])]

    @classmethod
    def mint(cls, user: User, ttl_minutes: int = 30) -> "PasswordResetToken":
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

