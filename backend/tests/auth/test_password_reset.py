"""
Password reset flow tests.
Covers: request throttling, per-email rate limit, token validity, confirm.
"""
import pytest
from django.utils import timezone
from datetime import timedelta

from apps.users.models import PasswordResetToken


@pytest.mark.django_db
class TestPasswordResetRequest:
    endpoint = "/api/auth/password-reset/request/"

    def test_valid_email_returns_200(self, api_client, admin_user):
        response = api_client.post(
            self.endpoint, {"email": "admin@test.com"}, format="json"
        )
        assert response.status_code == 200
        assert "detail" in response.data

    def test_nonexistent_email_returns_same_200(self, api_client):
        """Account enumeration prevention — same response for any email."""
        response = api_client.post(
            self.endpoint, {"email": "nobody@example.com"}, format="json"
        )
        assert response.status_code == 200

    def test_per_email_rate_limit_silently_drops_excess(self, api_client, admin_user):
        """HIGH-002: max 2 tokens per 15-minute window per email."""
        # First two should succeed (tokens created)
        api_client.post(self.endpoint, {"email": "admin@test.com"}, format="json")
        api_client.post(self.endpoint, {"email": "admin@test.com"}, format="json")

        # Third request in the window — should be silently dropped (still 200)
        response = api_client.post(
            self.endpoint, {"email": "admin@test.com"}, format="json"
        )
        assert response.status_code == 200
        # Only 2 tokens should exist
        assert PasswordResetToken.objects.filter(user=admin_user).count() == 2

    def test_token_is_created_in_database(self, api_client, admin_user):
        api_client.post(self.endpoint, {"email": "admin@test.com"}, format="json")
        assert PasswordResetToken.objects.filter(user=admin_user).exists()

    def test_inactive_user_gets_no_token(self, api_client, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(
            email="inactive@test.com",
            password="Pass123!",
            is_active=False,
        )
        api_client.post(
            self.endpoint, {"email": "inactive@test.com"}, format="json"
        )
        # Should NOT create a token for inactive users
        assert PasswordResetToken.objects.count() == 0


@pytest.mark.django_db
class TestPasswordResetConfirm:
    request_endpoint = "/api/auth/password-reset/request/"
    confirm_endpoint = "/api/auth/password-reset/confirm/"

    def test_valid_token_allows_password_change(self, api_client, admin_user):
        token_obj = PasswordResetToken.mint(user=admin_user, ttl_minutes=30)

        response = api_client.post(
            self.confirm_endpoint,
            {"token": token_obj.token, "new_password": "NewSecurePass123!"},
            format="json",
        )
        assert response.status_code == 200

        # Verify password was actually changed
        admin_user.refresh_from_db()
        assert admin_user.check_password("NewSecurePass123!")

    def test_expired_token_returns_400(self, api_client, admin_user):
        token_obj = PasswordResetToken.objects.create(
            user=admin_user,
            token="expired-token-value-12345",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = api_client.post(
            self.confirm_endpoint,
            {"token": token_obj.token, "new_password": "NewSecurePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_used_token_cannot_be_reused(self, api_client, admin_user):
        token_obj = PasswordResetToken.mint(user=admin_user, ttl_minutes=30)

        # First use
        api_client.post(
            self.confirm_endpoint,
            {"token": token_obj.token, "new_password": "NewSecurePass123!"},
            format="json",
        )

        # Second use — should fail
        response = api_client.post(
            self.confirm_endpoint,
            {"token": token_obj.token, "new_password": "AnotherPass456!"},
            format="json",
        )
        assert response.status_code == 400

    def test_invalid_token_returns_400(self, api_client):
        response = api_client.post(
            self.confirm_endpoint,
            {"token": "completely-fake-token", "new_password": "NewSecurePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_short_password_returns_400(self, api_client, admin_user):
        token_obj = PasswordResetToken.mint(user=admin_user, ttl_minutes=30)
        response = api_client.post(
            self.confirm_endpoint,
            {"token": token_obj.token, "new_password": "short"},
            format="json",
        )
        assert response.status_code == 400
