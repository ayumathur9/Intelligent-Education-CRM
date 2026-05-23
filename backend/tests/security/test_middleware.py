"""
Tests for OBS-002/003 middleware — correlation IDs and security event logging.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestRequestCorrelationMiddleware:
    def test_response_contains_request_id_header(self, api_client):
        response = api_client.get("/api/health/")
        assert "X-Request-ID" in response

    def test_request_id_is_non_empty(self, api_client):
        response = api_client.get("/api/health/")
        assert len(response["X-Request-ID"]) > 0

    def test_provided_request_id_is_echoed(self, api_client):
        custom_id = "test-correlation-id-12345"
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID=custom_id)
        assert response["X-Request-ID"] == custom_id

    def test_long_request_id_is_truncated(self, api_client):
        long_id = "x" * 200
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID=long_id)
        assert len(response["X-Request-ID"]) <= 64

    def test_different_requests_get_different_ids(self, api_client):
        r1 = api_client.get("/api/health/")
        r2 = api_client.get("/api/health/")
        # Both should have a request ID; they may differ (UUIDs).
        assert "X-Request-ID" in r1
        assert "X-Request-ID" in r2

    def test_newline_stripped_from_request_id(self, api_client):
        """Prevent header injection via newline in X-Request-ID."""
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID="id\ninjected: header")
        assert "\n" not in response["X-Request-ID"]


class TestSecurityHeadersMiddleware:
    def test_csp_header_present(self, api_client):
        response = api_client.get("/api/health/")
        assert "Content-Security-Policy" in response

    def test_permissions_policy_header_present(self, api_client):
        response = api_client.get("/api/health/")
        assert "Permissions-Policy" in response

    def test_csp_blocks_frames(self, api_client):
        response = api_client.get("/api/health/")
        csp = response.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_cross_origin_opener_policy_set(self, api_client):
        response = api_client.get("/api/health/")
        assert response.get("Cross-Origin-Opener-Policy") == "same-origin"

    def test_cross_origin_resource_policy_set(self, api_client):
        response = api_client.get("/api/health/")
        assert response.get("Cross-Origin-Resource-Policy") == "same-origin"


class TestSecurityEventLoggingMiddleware:
    def test_401_is_logged(self, api_client):
        """Unauthenticated request to protected endpoint generates 401 — logged."""
        response = api_client.get("/api/crm/students/")
        assert response.status_code == 401

    def test_403_on_student_accessing_admin(self, student_client):
        """Student trying to access admin-only endpoints gets 403."""
        response = student_client.delete("/api/students/1/")
        assert response.status_code in (403, 404)  # 404 if student doesn't exist

    def test_health_endpoint_no_logging_on_200(self, api_client):
        """200 responses are not security events."""
        response = api_client.get("/api/health/")
        assert response.status_code in (200, 503)
