"""
RL-001: Redis-backed throttling with burst protection and lockout escalation.

Falls back to DRF's default cache backend (LocMem in dev) when Redis is
unavailable, so tests and local development continue to work unmodified.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)

# After this many failures, block the IP/user for _LOCKOUT_DURATION_SECONDS.
_LOCKOUT_THRESHOLD = int(getattr(settings, "AUTH_LOCKOUT_THRESHOLD", 10))
_LOCKOUT_DURATION_SECONDS = int(getattr(settings, "AUTH_LOCKOUT_SECONDS", 900))  # 15 min


def _is_locked_out(scope: str, key: str) -> bool:
    """Return True if this key has been locked out."""
    lockout_key = f"throttle:lockout:{scope}:{key}"
    return bool(cache.get(lockout_key))


def _record_failure(scope: str, key: str) -> None:
    """Increment failure counter; trigger lockout when threshold is reached."""
    fail_key = f"throttle:failures:{scope}:{key}"
    failures = (cache.get(fail_key) or 0) + 1
    cache.set(fail_key, failures, timeout=_LOCKOUT_DURATION_SECONDS)

    if failures >= _LOCKOUT_THRESHOLD:
        lockout_key = f"throttle:lockout:{scope}:{key}"
        cache.set(lockout_key, True, timeout=_LOCKOUT_DURATION_SECONDS)
        logger.warning(
            "RL-001: %s locked out — %d failures exceeded threshold of %d",
            key, failures, _LOCKOUT_THRESHOLD,
        )
        try:
            from apps.audit.tasks import log_security_event
            log_security_event.delay(
                event_type="auth_lockout",
                user_id=None,
                ip_address=key,
                detail=f"Throttle scope={scope} exceeded {_LOCKOUT_THRESHOLD} failures",
            )
        except Exception:
            pass


def _get_client_ip(request) -> str:
    """HIGH-5: Extract trusted client IP using django-ipware when available."""
    try:
        from ipware import get_client_ip
        ip, _ = get_client_ip(request)
        return ip or "unknown"
    except ImportError:
        pass
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "unknown")


class LoginRateThrottle(AnonRateThrottle):
    """
    5 login attempts per minute per IP.
    Escalates to 15-minute lockout after 10 total failures.
    """
    scope = "login"

    def allow_request(self, request, view):
        ip = _get_client_ip(request)
        if _is_locked_out("login", ip):
            self.history = []  # Required by DRF's wait() method.
            return False

        allowed = super().allow_request(request, view)
        if not allowed:
            _record_failure("login", ip)
        return allowed


class PasswordResetRateThrottle(AnonRateThrottle):
    """3 password-reset requests per minute per IP."""
    scope = "password_reset"

    def allow_request(self, request, view):
        ip = _get_client_ip(request)
        if _is_locked_out("password_reset", ip):
            self.history = []  # Required by DRF's wait() method.
            return False
        return super().allow_request(request, view)


class RegisterRateThrottle(AnonRateThrottle):
    """
    RL-002: Limit new account creation to 10 per hour per IP.
    Prevents automated account spam, email service abuse, and
    email enumeration via repeated registration attempts.
    """
    scope = "register"


class UploadRateThrottle(UserRateThrottle):
    """
    RL-001: Limit file uploads to prevent storage abuse.
    Default: 30 uploads per minute per authenticated user.
    """
    scope = "upload"


class BurstProtectedUserThrottle(UserRateThrottle):
    """
    RL-001: Burst-protection throttle for sensitive API operations.
    Allows short bursts but enforces a tighter sustained limit.
    Default: 100 requests per minute per user.
    """
    scope = "burst"
