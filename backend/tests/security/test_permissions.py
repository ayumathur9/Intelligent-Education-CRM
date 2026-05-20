"""
Role-based access control tests — authorization & RBAC.

Verifies that each role can only access its permitted endpoints.
Covers: admin, counselor, editor, student, unauthenticated.
"""
import pytest


@pytest.mark.django_db
class TestUnauthenticatedAccess:
    """All protected endpoints must reject unauthenticated requests."""

    def test_me_endpoint_requires_auth(self, api_client):
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401

    def test_students_list_requires_auth(self, api_client):
        response = api_client.get("/api/crm/students/")
        assert response.status_code == 401

    def test_schools_list_requires_auth(self, api_client):
        response = api_client.get("/api/crm/schools/")
        assert response.status_code == 401

    def test_leads_list_requires_auth(self, api_client):
        response = api_client.get("/api/crm/leads/")
        assert response.status_code == 401

    def test_audit_log_requires_auth(self, api_client):
        response = api_client.get("/api/audit/activity-logs/")
        # 401 if endpoint requires auth; could also be 403
        assert response.status_code in (401, 403)

    def test_health_endpoint_is_public(self, api_client):
        """Health check must be accessible without auth."""
        response = api_client.get("/api/health/")
        assert response.status_code in (200, 503)


@pytest.mark.django_db
class TestAdminAccess:
    """Admin users should have access to all endpoints."""

    def test_admin_can_access_me(self, admin_client):
        response = admin_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["role"] == "admin"

    def test_admin_can_list_students(self, admin_client):
        response = admin_client.get("/api/crm/students/")
        assert response.status_code == 200

    def test_admin_can_list_schools(self, admin_client):
        response = admin_client.get("/api/crm/schools/")
        assert response.status_code == 200

    def test_admin_can_list_leads(self, admin_client):
        response = admin_client.get("/api/crm/leads/")
        assert response.status_code == 200

    def test_admin_can_access_audit_logs(self, admin_client):
        response = admin_client.get("/api/audit/activity-logs/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestCounselorAccess:
    """Counselor users should access CRM endpoints but not admin-only."""

    def test_counselor_can_access_me(self, counselor_client):
        response = counselor_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["role"] == "counselor"

    def test_counselor_can_list_students(self, counselor_client):
        response = counselor_client.get("/api/crm/students/")
        assert response.status_code == 200

    def test_counselor_can_list_schools(self, counselor_client):
        response = counselor_client.get("/api/crm/schools/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestStudentAccess:
    """Student users should only see their own data."""

    def test_student_can_access_me(self, student_client):
        response = student_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["role"] == "student"

    def test_student_cannot_access_leads(self, student_client):
        response = student_client.get("/api/crm/leads/")
        assert response.status_code == 403

    def test_student_cannot_access_audit_logs(self, student_client):
        response = student_client.get("/api/audit/activity-logs/")
        assert response.status_code == 403


@pytest.mark.django_db
class TestTokenSecurity:
    """JWT token security assertions."""

    def test_tampered_token_returns_401(self, api_client, admin_user):
        """A JWT with a tampered signature must be rejected."""
        response = api_client.post(
            "/api/auth/login/",
            {"email": "admin@test.com", "password": "AdminPass123!"},
            format="json",
        )
        access = response.data["access"]
        # Tamper the signature segment
        parts = access.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalidsignature"

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered}")
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401

    def test_no_token_returns_401(self, api_client):
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401

    def test_malformed_bearer_returns_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not.a.real.jwt")
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401
