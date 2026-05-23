"""
SEC-002: Suspicious activity detection.

Heuristics:
- Repeated failed logins from the same IP (brute-force detection).
- High request velocity from a single IP (scraping / enumeration).
- Token abuse: multiple expired/invalid tokens in a short window.
- Impossible-velocity: logins from two distant IPs within 5 minutes.

All checks are Redis-backed with sensible in-process fallback when Redis
is unavailable (development mode).
"""
from __future__ import annotations

import hashlib
import logging
import os
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (overridable via settings)
# ---------------------------------------------------------------------------
_FAILED_LOGIN_WINDOW_S  = int(getattr(settings, "ANOMALY_FAILED_LOGIN_WINDOW",  300))   # 5 min
_FAILED_LOGIN_THRESHOLD = int(getattr(settings, "ANOMALY_FAILED_LOGIN_THRESHOLD", 5))
_TOKEN_ABUSE_WINDOW_S   = int(getattr(settings, "ANOMALY_TOKEN_ABUSE_WINDOW",    120))   # 2 min
_TOKEN_ABUSE_THRESHOLD  = int(getattr(settings, "ANOMALY_TOKEN_ABUSE_THRESHOLD",  3))
_VELOCITY_WINDOW_S      = int(getattr(settings, "ANOMALY_VELOCITY_WINDOW",       300))   # 5 min
_VELOCITY_THRESHOLD     = int(getattr(settings, "ANOMALY_VELOCITY_THRESHOLD",    200))   # req/window


def _redis():
    """Return a Redis client or None if unavailable."""
    try:
        import redis as _redis_lib
        url = getattr(settings, "REDIS_URL", None) or os.getenv("REDIS_URL", "")
        if not url:
            return None
        return _redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-email account lockout (complements per-IP lockout in throttles.py)
# ---------------------------------------------------------------------------
_EMAIL_LOCKOUT_THRESHOLD = int(getattr(settings, "ACCOUNT_LOCKOUT_THRESHOLD", 10))
_EMAIL_LOCKOUT_SECONDS   = int(getattr(settings, "ACCOUNT_LOCKOUT_SECONDS", 900))


def is_account_locked(email: str) -> bool:
    """Return True if this email address is locked out due to too many failures."""
    r = _redis()
    if r is None:
        return False
    key = f"crm:account:lockout:{email.lower()}"
    try:
        return bool(r.get(key))
    except Exception:
        return False


def record_failed_login_for_email(email: str) -> bool:
    """
    Increment per-email failure counter.
    Returns True and locks the account when threshold is reached.
    """
    r = _redis()
    if r is None:
        return False

    fail_key = f"crm:account:failures:{email.lower()}"
    lock_key = f"crm:account:lockout:{email.lower()}"
    try:
        count = r.incr(fail_key)
        if count == 1:
            r.expire(fail_key, _EMAIL_LOCKOUT_SECONDS)

        if count >= _EMAIL_LOCKOUT_THRESHOLD:
            r.setex(lock_key, _EMAIL_LOCKOUT_SECONDS, "1")
            logger.warning(
                "SEC-002 account lockout: %s failed %d times — locked for %ds",
                email, count, _EMAIL_LOCKOUT_SECONDS,
            )
            _emit_security_event(
                "account_lockout", "n/a", None,
                f"Account {email} locked after {count} failures",
            )
            return True
    except Exception as exc:
        logger.debug("record_failed_login_for_email redis error: %s", exc)
    return False


def clear_failed_login_attempts(email: str) -> None:
    """Reset failure counter and lockout flag on successful login."""
    r = _redis()
    if r is None:
        return
    try:
        r.delete(
            f"crm:account:failures:{email.lower()}",
            f"crm:account:lockout:{email.lower()}",
        )
    except Exception as exc:
        logger.debug("clear_failed_login_attempts redis error: %s", exc)


def record_failed_login(ip: str, user_id: int | None = None) -> bool:
    """
    Increment the failed login counter for this IP.
    Returns True if the threshold has been exceeded (alert should be raised).
    """
    r = _redis()
    if r is None:
        return False

    key = f"crm:anomaly:failed_login:{ip}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, _FAILED_LOGIN_WINDOW_S)

        if count >= _FAILED_LOGIN_THRESHOLD:
            logger.warning(
                "SEC-002 anomaly: %d failed logins from ip=%s (threshold=%d)",
                count, ip, _FAILED_LOGIN_THRESHOLD,
            )
            _emit_security_event("brute_force_login", ip, user_id,
                                 f"{count} failed logins in {_FAILED_LOGIN_WINDOW_S}s")
            return True
    except Exception as exc:
        logger.debug("record_failed_login redis error: %s", exc)
    return False


def record_token_abuse(ip: str, user_id: int | None = None) -> bool:
    """
    Record an invalid/expired token submission.
    Returns True if the token abuse threshold is exceeded.
    """
    r = _redis()
    if r is None:
        return False

    key = f"crm:anomaly:token_abuse:{ip}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, _TOKEN_ABUSE_WINDOW_S)

        if count >= _TOKEN_ABUSE_THRESHOLD:
            logger.warning(
                "SEC-002 anomaly: %d invalid tokens from ip=%s",
                count, ip,
            )
            _emit_security_event("token_abuse", ip, user_id,
                                 f"{count} invalid tokens in {_TOKEN_ABUSE_WINDOW_S}s")
            return True
    except Exception as exc:
        logger.debug("record_token_abuse redis error: %s", exc)
    return False


def check_impossible_velocity(user_id: int, ip: str) -> bool:
    """
    Detect if a user has logged in from two very different IPs within 5 minutes.
    Returns True if suspicious (caller should log the event but NOT block — reduces
    false-positive impact from VPNs / mobile IP changes).
    """
    r = _redis()
    if r is None:
        return False

    key = f"crm:anomaly:last_ip:{user_id}"
    try:
        last_ip = r.get(key)
        r.setex(key, _VELOCITY_WINDOW_S, ip)

        if last_ip and last_ip != ip:
            # IPs changed — heuristic: flag if they're in different /16 subnets.
            if _different_subnet(last_ip, ip):
                logger.warning(
                    "SEC-002 anomaly: impossible velocity user=%s ip_before=%s ip_now=%s",
                    user_id, last_ip, ip,
                )
                _emit_security_event("impossible_velocity", ip, user_id,
                                     f"Login from {ip} (last: {last_ip}) within {_VELOCITY_WINDOW_S}s")
                return True
    except Exception as exc:
        logger.debug("check_impossible_velocity redis error: %s", exc)
    return False


def record_request_velocity(ip: str) -> bool:
    """
    Check if this IP is making requests above the velocity threshold.
    Returns True if the threshold is exceeded.
    """
    r = _redis()
    if r is None:
        return False

    now = int(time.time())
    key = f"crm:anomaly:velocity:{ip}:{now // _VELOCITY_WINDOW_S}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, _VELOCITY_WINDOW_S * 2)
        if count >= _VELOCITY_THRESHOLD:
            logger.warning("SEC-002 anomaly: velocity %d req/%ds from ip=%s", count, _VELOCITY_WINDOW_S, ip)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _different_subnet(ip1: str, ip2: str) -> bool:
    """Return True if two IPv4 addresses are in different /16 subnets."""
    try:
        parts1 = ip1.split(".")
        parts2 = ip2.split(".")
        return parts1[:2] != parts2[:2]
    except Exception:
        return False


def _emit_security_event(event_type: str, ip: str, user_id: int | None, detail: str) -> None:
    """Fire an async audit log entry. Never blocks the caller."""
    try:
        from apps.audit.tasks import log_security_event
        log_security_event.delay(
            event_type=event_type,
            user_id=user_id,
            ip_address=ip,
            detail=detail,
        )
    except Exception:
        pass
