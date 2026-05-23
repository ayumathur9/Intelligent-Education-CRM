from __future__ import annotations

import logging
import threading
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)

# Thread-local storage for the current request's correlation ID.
# Accessible from anywhere in the call stack (views, tasks, signals).
_request_id_local = threading.local()


def get_request_id() -> str:
    """Return the current request's correlation ID, or a new UUID if none is set."""
    return getattr(_request_id_local, "request_id", str(uuid.uuid4()))


class RequestCorrelationMiddleware:
    """
    OBS-002: Assign a unique X-Request-ID to every request.

    - Reads X-Request-ID from the incoming request header if provided by an
      upstream proxy (e.g. Railway, nginx) so the same trace ID propagates
      end-to-end.
    - Generates a fresh UUID4 when none is supplied.
    - Stores the ID in thread-local storage so log records and Celery tasks
      can include it without explicit parameter threading.
    - Echoes the ID back in the response header for client-side correlation.
    """

    HEADER_NAME = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (
            request.headers.get(self.HEADER_NAME)
            or request.META.get("HTTP_X_REQUEST_ID")
            or str(uuid.uuid4())
        )
        # Sanitise: only allow safe characters.
        request_id = request_id[:64].replace("\n", "").replace("\r", "")

        _request_id_local.request_id = request_id
        request.request_id = request_id

        response = self.get_response(request)
        response[self.HEADER_NAME] = request_id
        return response


class SecurityHeadersMiddleware:
    """Adds CSP and Permissions-Policy headers to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if "Content-Security-Policy" not in response:
            supabase_origin = ""
            if settings.SUPABASE_URL:
                from urllib.parse import urlparse
                parsed = urlparse(settings.SUPABASE_URL)
                supabase_origin = f"{parsed.scheme}://{parsed.netloc}"

            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                f"img-src 'self' data: blob: {supabase_origin}; "
                "font-src 'self' https://fonts.gstatic.com; "
                f"connect-src 'self' ws: wss: {supabase_origin}; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )

        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # SEC-001: COOP prevents cross-origin window references (popups, iframes).
        # CORP limits which origins can embed our resources in no-cors requests.
        # COEP is intentionally omitted: require-corp would block Tailwind CDN, Google Fonts,
        # and supabase-js (none of which ship a Cross-Origin-Resource-Policy header), breaking
        # the entire UI. COEP is only safe when ALL resources are same-origin or cooperating CDNs.
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")

        return response


class SecurityEventLoggingMiddleware:
    """
    OBS-003: Log security-relevant events at the response layer.

    Captures:
    - 401 Unauthenticated responses (token missing / expired)
    - 403 Permission denied (RBAC violation)
    - 429 Rate limited requests
    - 400 Bad request on auth endpoints (potential credential stuffing)
    """

    _SECURITY_PATHS = {"/api/auth/", "/api/users/", "/api/health/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        status_code = response.status_code
        if status_code not in (400, 401, 403, 429):
            return response

        path = request.path_info
        method = request.method
        user_id = getattr(getattr(request, "user", None), "pk", None)
        ip = self._get_ip(request)
        request_id = getattr(request, "request_id", "")

        event_map = {
            400: "bad_request",
            401: "unauthenticated",
            403: "permission_denied",
            429: "rate_limited",
        }
        event_type = event_map[status_code]

        logger.warning(
            "security_event type=%s method=%s path=%s status=%d user=%s ip=%s request_id=%s",
            event_type,
            method,
            path,
            status_code,
            user_id,
            ip,
            request_id,
            extra={
                "event_type": event_type,
                "path": path,
                "status_code": status_code,
                "user_id": user_id,
                "ip": ip,
                "request_id": request_id,
            },
        )

        # Only persist security events for auth/permission failures (not every 400).
        if status_code in (401, 403, 429):
            try:
                from apps.audit.tasks import log_security_event
                log_security_event.delay(
                    event_type=event_type,
                    user_id=user_id,
                    ip_address=ip or "",
                    detail=f"{method} {path} → {status_code}",
                )
            except Exception:
                # Never block the response for a logging side-effect.
                pass

        return response

    @staticmethod
    def _get_ip(request) -> str:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
