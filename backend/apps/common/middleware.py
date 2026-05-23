from __future__ import annotations

import logging
import re
import threading
import uuid

logger = logging.getLogger(__name__)

# Thread-local storage for the current request's correlation ID.
# Accessible from anywhere in the call stack (views, tasks, signals).
_request_id_local = threading.local()


class RequestIdFilter(logging.Filter):
    """OBS-002: Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(_request_id_local, "request_id", "-")
        return True


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
        raw_id = (
            request.headers.get(self.HEADER_NAME)
            or request.META.get("HTTP_X_REQUEST_ID")
            or ""
        )
        # MED-6: Strip any character outside [a-zA-Z0-9\-_] to prevent log injection.
        request_id = re.sub(r"[^a-zA-Z0-9\-_]", "", raw_id)[:64] or str(uuid.uuid4())

        _request_id_local.request_id = request_id
        request.request_id = request_id

        response = self.get_response(request)
        response[self.HEADER_NAME] = request_id
        return response


class CspNonceMiddleware:
    """
    HIGH-4: Generate a per-request CSP nonce and expose it on the request object.

    Usage in templates: <script nonce="{{ request.csp_nonce }}">...</script>
    The nonce is a URL-safe base64 random value regenerated for every request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import base64
        import os as _os
        request.csp_nonce = base64.urlsafe_b64encode(_os.urandom(16)).decode("ascii")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Adds CSP (with nonce) and Permissions-Policy headers to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        nonce = getattr(request, "csp_nonce", "")
        nonce_src = f"'nonce-{nonce}'" if nonce else ""

        if "Content-Security-Policy" not in response:
            # HIGH-4: nonce replaces 'unsafe-inline' for scripts; inline styles still
            # need 'unsafe-inline' because Tailwind CDN injects style attributes at runtime.
            script_src = (
                f"'self' {nonce_src} https://cdn.tailwindcss.com https://cdn.jsdelivr.net"
                if nonce_src
                else "'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net 'unsafe-inline'"
            )
            response["Content-Security-Policy"] = (
                f"default-src 'self'; "
                f"script-src {script_src}; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: blob:; "
                "font-src 'self' https://fonts.gstatic.com; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )

        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # SEC-001: COOP prevents cross-origin window references (popups, iframes).
        # CORP limits which origins can embed our resources in no-cors requests.
        # COEP is intentionally omitted: require-corp would block Tailwind CDN and Google Fonts
        # (neither ship a Cross-Origin-Resource-Policy header). Safe to add once all CDN resources
        # are replaced with self-hosted equivalents.
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
        # HIGH-5: Use django-ipware when available for trusted proxy IP extraction.
        try:
            from ipware import get_client_ip
            ip, _ = get_client_ip(request)
            return ip or ""
        except ImportError:
            pass
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
