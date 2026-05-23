"""
Tests for the authenticated media proxy view (CRIT-1).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from django.test import override_settings


@pytest.fixture
def media_dir(tmp_path):
    """Create a temporary MEDIA_ROOT with a test file."""
    media = tmp_path / "media"
    media.mkdir()
    (media / "uploads").mkdir()
    test_file = media / "uploads" / "test-file.pdf"
    test_file.write_bytes(b"%PDF-1.4 fake content")
    return media


@pytest.mark.django_db
def test_media_proxy_requires_auth(client, media_dir):
    """Unauthenticated requests to /media/ must return 401."""
    with override_settings(MEDIA_ROOT=str(media_dir)):
        response = client.get("/media/uploads/test-file.pdf")
    assert response.status_code == 401


@pytest.mark.django_db
def test_media_proxy_authenticated_access(admin_client, media_dir):
    """Authenticated admin can access media files."""
    with override_settings(MEDIA_ROOT=str(media_dir), NGINX_MEDIA_ACCEL=False):
        response = admin_client.get("/media/uploads/test-file.pdf")
    assert response.status_code == 200


@pytest.mark.django_db
def test_media_proxy_path_traversal_blocked(admin_client, media_dir, tmp_path):
    """Path traversal attempts must be rejected with 404."""
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive data")
    with override_settings(MEDIA_ROOT=str(media_dir), NGINX_MEDIA_ACCEL=False):
        response = admin_client.get("/media/../secret.txt")
    assert response.status_code in (404, 400)


@pytest.mark.django_db
def test_media_proxy_nonexistent_file(admin_client, media_dir):
    """Requesting a non-existent file returns 404."""
    with override_settings(MEDIA_ROOT=str(media_dir), NGINX_MEDIA_ACCEL=False):
        response = admin_client.get("/media/uploads/does-not-exist.pdf")
    assert response.status_code == 404


@pytest.mark.django_db
def test_media_proxy_nginx_accel(admin_client, media_dir):
    """When NGINX_MEDIA_ACCEL is enabled, response contains X-Accel-Redirect."""
    with override_settings(MEDIA_ROOT=str(media_dir), NGINX_MEDIA_ACCEL=True):
        response = admin_client.get("/media/uploads/test-file.pdf")
    assert response.status_code == 200
    assert "X-Accel-Redirect" in response
    assert response["X-Accel-Redirect"] == "/protected-media/uploads/test-file.pdf"
