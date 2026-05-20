"""
Shared pytest fixtures for the Intelligent Education CRM test suite.
All tests import from here via pytest's automatic conftest discovery.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

User = get_user_model()

# ---------------------------------------------------------------------------
# Throttle override
# DRF throttling uses the real IP (127.0.0.1) for all test requests, which
# causes tests to trip the rate limiter after a few calls.
# We disable throttling globally for the test session.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def disable_throttling(settings):
    """
    Neutralise DRF rate limiting for all tests.

    Setting all throttle rates to "10000/second" keeps the throttle
    class pipeline intact (so views with hardcoded throttle_classes don't
    blow up with ImproperlyConfigured) but allows unlimited test calls.
    """
    high_rate = "10000/second"
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ]
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        "anon": high_rate,
        "user": high_rate,
        "login": high_rate,
        "password_reset": high_rate,
    }


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@test.com",
        password="AdminPass123!",
        full_name="Test Admin",
        role="admin",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def counselor_user(db):
    return User.objects.create_user(
        email="counselor@test.com",
        password="CounselorPass123!",
        full_name="Test Counselor",
        role="counselor",
    )


@pytest.fixture
def editor_user(db):
    return User.objects.create_user(
        email="editor@test.com",
        password="EditorPass123!",
        full_name="Test Editor",
        role="editor",
    )


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        email="student@test.com",
        password="StudentPass123!",
        full_name="Test Student",
        role="student",
    )


# ---------------------------------------------------------------------------
# Authenticated API client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def counselor_client(counselor_user):
    client = APIClient()
    client.force_authenticate(user=counselor_user)
    return client


@pytest.fixture
def editor_client(editor_user):
    client = APIClient()
    client.force_authenticate(user=editor_user)
    return client


@pytest.fixture
def student_client(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)
    return client


# ---------------------------------------------------------------------------
# JWT token fixtures — login to get real JWT tokens
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_tokens(admin_user, api_client):
    response = api_client.post(
        "/api/auth/login/",
        {"email": "admin@test.com", "password": "AdminPass123!"},
        format="json",
    )
    assert response.status_code == 200, f"Login failed: {response.data}"
    return response.data


@pytest.fixture
def counselor_tokens(counselor_user, api_client):
    response = api_client.post(
        "/api/auth/login/",
        {"email": "counselor@test.com", "password": "CounselorPass123!"},
        format="json",
    )
    assert response.status_code == 200, f"Login failed: {response.data}"
    return response.data
