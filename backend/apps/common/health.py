"""
Health check endpoint — HIGH-006.

Returns the operational status of all critical infrastructure dependencies.
Used by Railway for deployment validation and by external uptime monitors.

GET /api/health/
  200 OK        — all dependencies healthy
  503 Service Unavailable — one or more dependencies unreachable
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection, OperationalError as DbOperationalError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def _check_database() -> tuple[bool, str]:
    """Probe the primary database with a cheap query."""
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, "ok"
    except DbOperationalError as exc:
        logger.error("Health check: database unreachable — %s", exc)
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Health check: database error — %s", exc)
        return False, "unexpected error"


def _check_redis() -> tuple[bool, str]:
    """
    Probe Redis only when the Redis channel layer is configured.
    Returns (True, "not_configured") when REDIS_URL is not set
    so that health degrades gracefully in local dev.
    """
    redis_url = getattr(settings, "_REDIS_URL", "") or ""
    if not redis_url:
        # Local dev or staging without Redis — non-fatal.
        return True, "not_configured"

    try:
        import redis  # type: ignore[import]
        client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Health check: Redis unreachable — %s", exc)
        return False, "unreachable"


def _check_storage() -> tuple[bool, str]:
    """
    Probe Supabase Storage when configured.
    Returns (True, "not_configured") in local dev without Supabase credentials.
    """
    if not getattr(settings, "SUPABASE_URL", "") or not getattr(
        settings, "SUPABASE_SERVICE_ROLE_KEY", ""
    ):
        return True, "not_configured"

    try:
        from apps.common.storage.supabase_storage import supabase_healthy
        ok = supabase_healthy()
        return ok, "ok" if ok else "unreachable"
    except Exception as exc:  # noqa: BLE001
        logger.error("Health check: Supabase Storage unreachable — %s", exc)
        return False, "unreachable"


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Infrastructure health probe.

    Checks:
    - Database connectivity
    - Redis connectivity (when configured)
    - Supabase Storage (when configured)

    Returns HTTP 200 if all configured dependencies are healthy,
    HTTP 503 if any dependency is down.
    """
    db_ok, db_status = _check_database()
    redis_ok, redis_status = _check_redis()
    storage_ok, storage_status = _check_storage()

    all_ok = db_ok and redis_ok and storage_ok

    payload = {
        "status": "ok" if all_ok else "degraded",
        "service": "intelligent-education-crm",
        "checks": {
            "database": db_status,
            "redis": redis_status,
            "storage": storage_status,
        },
    }

    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(payload, status=http_status)
