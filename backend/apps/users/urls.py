from django.urls import path

from .views import (
    BroadcastEmailView,
    EmailVerifyView,
    InviteAcceptView,
    InviteCreateView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    RegisterView,
)
from .mfa_views import MFADisableView, MFASetupView, MFAStatusView, MFAVerifyView

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),        # HIGH-001
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    # HIGH-2: Email verification link handler.
    path("auth/verify-email/", EmailVerifyView.as_view(), name="email-verify"),
    # LOW-009: TOTP/MFA endpoints for admin and counselor accounts.
    path("auth/invite/", InviteCreateView.as_view(), name="invite-create"),
    path("auth/invite/accept/", InviteAcceptView.as_view(), name="invite-accept"),
    path("admin/broadcast-email/", BroadcastEmailView.as_view(), name="admin-broadcast-email"),
    path("auth/mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("auth/mfa/verify/", MFAVerifyView.as_view(), name="mfa-verify"),
    path("auth/mfa/disable/", MFADisableView.as_view(), name="mfa-disable"),
    path("auth/mfa/status/", MFAStatusView.as_view(), name="mfa-status"),
]
