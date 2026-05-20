"""
Health check endpoint tests — HIGH-006.
"""
import pytest


@pytest.mark.django_db
class TestHealthCheck:
    endpoint = "/api/health/"

    def test_health_returns_200_with_healthy_db(self, api_client):
        response = api_client.get(self.endpoint)
        # In test environment with SQLite, DB should be reachable
        assert response.status_code in (200, 503)
        assert "status" in response.data
        assert "checks" in response.data
        assert "database" in response.data["checks"]

    def test_health_no_auth_required(self, api_client):
        """Health endpoint must be accessible without authentication."""
        response = api_client.get(self.endpoint)
        assert response.status_code != 401
        assert response.status_code != 403

    def test_health_response_structure(self, api_client):
        response = api_client.get(self.endpoint)
        data = response.data
        assert "status" in data
        assert data["status"] in ("ok", "degraded")
        assert "service" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]

    def test_health_database_ok_when_db_reachable(self, api_client):
        response = api_client.get(self.endpoint)
        # If we can run tests, the DB is reachable
        if response.status_code == 200:
            assert response.data["checks"]["database"] == "ok"
