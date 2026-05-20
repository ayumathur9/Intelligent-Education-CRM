"""
Logout tests — HIGH-001.
Verifies that the logout endpoint blacklists the refresh token.
"""
import pytest
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.mark.django_db
class TestLogout:
    login_endpoint = "/api/auth/login/"
    logout_endpoint = "/api/auth/logout/"
    refresh_endpoint = "/api/auth/refresh/"

    def _login(self, api_client, user, password):
        response = api_client.post(
            self.login_endpoint,
            {"email": user.email, "password": password},
            format="json",
        )
        return response.data

    def test_logout_returns_204(self, api_client, admin_user):
        tokens = self._login(api_client, admin_user, "AdminPass123!")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = api_client.post(
            self.logout_endpoint,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        assert response.status_code == 204

    def test_blacklisted_token_cannot_be_refreshed(self, api_client, admin_user):
        tokens = self._login(api_client, admin_user, "AdminPass123!")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        # Logout — blacklists the refresh token
        api_client.post(
            self.logout_endpoint,
            {"refresh": tokens["refresh"]},
            format="json",
        )

        # Attempting to use the blacklisted refresh token should fail
        response = api_client.post(
            self.refresh_endpoint,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        assert response.status_code == 401

    def test_logout_without_refresh_token_still_returns_204(self, api_client, admin_user):
        """Logout should never fail the client even if no token provided."""
        tokens = self._login(api_client, admin_user, "AdminPass123!")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = api_client.post(self.logout_endpoint, {}, format="json")
        assert response.status_code == 204

    def test_unauthenticated_logout_returns_401(self, api_client):
        """Logout endpoint requires authentication."""
        response = api_client.post(
            self.logout_endpoint,
            {"refresh": "fake-token"},
            format="json",
        )
        assert response.status_code == 401

    def test_invalid_refresh_token_still_returns_204(self, api_client, admin_user):
        """Invalid/expired tokens should not cause logout to fail."""
        tokens = self._login(api_client, admin_user, "AdminPass123!")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = api_client.post(
            self.logout_endpoint,
            {"refresh": "invalid.token.here"},
            format="json",
        )
        assert response.status_code == 204
