from __future__ import annotations

from django.conf import settings


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
                # Tailwind CDN + any inline <script> blocks (needed for tailwind.config)
                "script-src 'self' https://cdn.tailwindcss.com 'unsafe-inline'; "
                # Inline styles + Google Fonts CSS
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                # Images: self, data URIs, blobs, Supabase storage
                f"img-src 'self' data: blob: {supabase_origin}; "
                # Google Fonts actual font files
                "font-src 'self' https://fonts.gstatic.com; "
                # API calls + WebSockets: self + Supabase
                f"connect-src 'self' ws: wss: {supabase_origin}; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )

        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
