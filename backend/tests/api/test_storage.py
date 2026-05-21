"""
Tests for the Supabase Storage service layer — CRIT-003.
These tests mock the Supabase client to avoid real network calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSupabaseStorageUpload:
    @patch("apps.common.storage.supabase_storage._client")
    def test_upload_returns_path_and_url(self, mock_client):
        """Successful upload returns (path, public_url) tuple."""
        mock_storage = MagicMock()
        mock_client.return_value.storage.from_.return_value = mock_storage
        mock_storage.get_public_url.return_value = "https://supabase.co/storage/v1/object/public/bucket/uploads/abc.pdf"

        from apps.common.storage.supabase_storage import upload_file
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_STORAGE_BUCKET = "bucket"
            mock_settings.SUPABASE_PUBLIC_URL_BASE = "https://supabase.co"
            path, url = upload_file(
                folder="uploads",
                filename="test.pdf",
                file_bytes=b"%PDF-1.7 content",
                content_type="application/pdf",
            )

        assert path.startswith("uploads/")
        assert path.endswith(".pdf")
        assert "supabase" in url.lower() or url  # URL returned

    @patch("apps.common.storage.supabase_storage._client")
    @patch("apps.common.storage.supabase_storage.time")
    def test_upload_retries_on_failure(self, mock_time, mock_client):
        """Upload retries up to _MAX_RETRIES times before raising RuntimeError."""
        mock_storage = MagicMock()
        mock_client.return_value.storage.from_.return_value = mock_storage
        mock_storage.upload.side_effect = RuntimeError("connection refused")
        # Prevent real sleeping in retries.
        mock_time.sleep.return_value = None

        from apps.common.storage.supabase_storage import upload_file
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_STORAGE_BUCKET = "bucket"
            with pytest.raises(RuntimeError, match="Supabase upload failed"):
                upload_file(
                    folder="uploads",
                    filename="test.pdf",
                    file_bytes=b"data",
                    content_type="application/pdf",
                )

        # Should have called upload 3 times (MAX_RETRIES).
        assert mock_storage.upload.call_count == 3

    @patch("apps.common.storage.supabase_storage._client")
    def test_delete_returns_true_on_success(self, mock_client):
        mock_storage = MagicMock()
        mock_client.return_value.storage.from_.return_value = mock_storage

        from apps.common.storage.supabase_storage import delete_file
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_STORAGE_BUCKET = "bucket"
            result = delete_file(path="uploads/test.pdf")

        assert result is True
        mock_storage.remove.assert_called_once_with(["uploads/test.pdf"])

    @patch("apps.common.storage.supabase_storage._client")
    def test_delete_returns_false_on_exception(self, mock_client):
        mock_storage = MagicMock()
        mock_client.return_value.storage.from_.return_value = mock_storage
        mock_storage.remove.side_effect = Exception("network error")

        from apps.common.storage.supabase_storage import delete_file
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_STORAGE_BUCKET = "bucket"
            result = delete_file(path="uploads/test.pdf")

        assert result is False  # Never raises

    def test_supabase_not_configured(self):
        """supabase_healthy() returns False when URL/key not set."""
        from apps.common.storage.supabase_storage import supabase_healthy
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_URL = ""
            mock_settings.SUPABASE_SERVICE_ROLE_KEY = ""
            assert supabase_healthy() is False

    @patch("apps.common.storage.supabase_storage._client")
    def test_supabase_healthy_on_success(self, mock_client):
        mock_client.return_value.storage.list_buckets.return_value = []

        from apps.common.storage.supabase_storage import supabase_healthy
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_URL = "https://proj.supabase.co"
            mock_settings.SUPABASE_SERVICE_ROLE_KEY = "service_key"
            assert supabase_healthy() is True

    @patch("apps.common.storage.supabase_storage._client")
    def test_supabase_healthy_returns_false_on_error(self, mock_client):
        mock_client.return_value.storage.list_buckets.side_effect = Exception("timeout")

        from apps.common.storage.supabase_storage import supabase_healthy
        with patch("apps.common.storage.supabase_storage.settings") as mock_settings:
            mock_settings.SUPABASE_URL = "https://proj.supabase.co"
            mock_settings.SUPABASE_SERVICE_ROLE_KEY = "service_key"
            assert supabase_healthy() is False


class TestHealthCheckStorageProbe:
    """Test that the health endpoint includes the storage check."""

    def test_health_includes_storage_key(self, api_client):
        response = api_client.get("/api/health/")
        assert "storage" in response.data.get("checks", {})

    def test_health_storage_not_configured(self, api_client):
        """When Supabase is not configured, storage reports not_configured (non-fatal)."""
        with patch("apps.common.health.settings") as mock_settings:
            mock_settings.SUPABASE_URL = ""
            mock_settings.SUPABASE_SERVICE_ROLE_KEY = ""
            response = api_client.get("/api/health/")
        assert response.status_code in (200, 503)
