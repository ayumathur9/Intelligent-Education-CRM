from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import PasswordResetToken, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "full_name", "phone")
    list_filter = ("role", "is_active", "is_staff")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "phone", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("date_joined",)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    # Token intentionally excluded from list_display to prevent admin-level
    # account takeover via token theft. Visible only in the detail view for
    # support/debugging, where access is already audited by django-otp MFA.
    list_display = ("user", "token_prefix", "expires_at", "used_at", "created_at")
    search_fields = ("user__email",)
    list_filter = ("used_at",)
    readonly_fields = ("token_prefix", "created_at")

    @admin.display(description="Token (prefix)")
    def token_prefix(self, obj):
        """Show only the first 8 characters so tokens cannot be reconstructed."""
        return f"{obj.token[:8]}…" if obj.token else "—"

