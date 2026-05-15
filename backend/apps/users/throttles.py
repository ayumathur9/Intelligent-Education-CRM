from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """5 login attempts per minute per IP (scope defined in DRF_THROTTLE_RATES)."""
    scope = "login"


class PasswordResetRateThrottle(AnonRateThrottle):
    """3 password-reset requests per minute per IP."""
    scope = "password_reset"
