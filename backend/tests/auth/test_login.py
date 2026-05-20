"""
Authentication tests — login, token structure, inactive users.
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestLogin:
    endpoint = "/api/auth/login/"

    def test_valid_credentials_return_tokens_and_user(self, api_client, admin_user):
        response = api_client.post(
            self.endpoint,
            {"email": "admin@test.com", "password": "AdminPass123!"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        assert "user" in response.data
        assert response.data["user"]["email"] == "admin@test.com"

    def test_invalid_password_returns_400(self, api_client, admin_user):
        response = api_client.post(
            self.endpoint,
            {"email": "admin@test.com", "password": "WrongPassword!"},
            format="json",
        )
        assert response.status_code == 400

    def test_nonexistent_email_returns_400(self, api_client):
        response = api_client.post(
            self.endpoint,
            {"email": "nobody@test.com", "password": "SomePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_inactive_user_cannot_login(self, api_client, db):
        user = User.objects.create_user(
            email="inactive@test.com",
            password="InactivePass123!",
            is_active=False,
        )
        response = api_client.post(
            self.endpoint,
            {"email": "inactive@test.com", "password": "InactivePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_missing_email_returns_400(self, api_client):
        response = api_client.post(
            self.endpoint,
            {"password": "SomePass123!"},
            format="json",
        )
        assert response.status_code == 400

    def test_missing_password_returns_400(self, api_client):
        response = api_client.post(
            self.endpoint,
            {"email": "admin@test.com"},
            format="json",
        )
        assert response.status_code == 400

    def test_empty_body_returns_400(self, api_client):
        response = api_client.post(self.endpoint, {}, format="json")
        assert response.status_code == 400

    def test_role_is_included_in_response(self, api_client, counselor_user):
        response = api_client.post(
            self.endpoint,
            {"email": "counselor@test.com", "password": "CounselorPass123!"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["user"]["role"] == "counselor"
