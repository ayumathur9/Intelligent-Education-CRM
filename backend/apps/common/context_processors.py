"""
SEC-CSP: Inject the per-request CSP nonce into Django template context.

Add to TEMPLATES[0]["OPTIONS"]["context_processors"] in settings.py:
    "apps.common.context_processors.csp_nonce",

Usage in templates:
    <script nonce="{{ csp_nonce }}">...</script>
    <style nonce="{{ csp_nonce }}">...</style>
"""


def csp_nonce(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}
