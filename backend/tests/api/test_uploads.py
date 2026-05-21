"""
Upload security tests — HIGH-008 integration with file upload view.
"""
from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


UPLOAD_URL = "/api/files/upload/"

# Valid JPEG magic bytes
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 200
_PDF_BYTES = b"%PDF-1.7\n%%EOF\n"
_PE_BYTES = b"MZ\x90\x00" + b"\x00" * 200


class TestUploadSecurityLayer:
    """File upload blocked by scanner before reaching storage."""

    def test_clean_jpeg_allowed(self, admin_client):
        with patch("apps.files.views._supabase_configured", return_value=False):
            with patch("django.core.files.storage.default_storage.save", return_value="uploads/test.jpg"):
                with patch("django.core.files.storage.default_storage.url", return_value="/media/uploads/test.jpg"):
                    f = SimpleUploadedFile("photo.jpg", _JPEG_BYTES, content_type="image/jpeg")
                    resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        # Either 201 (uploaded) or 502 (local storage unavailable) — not 400.
        assert resp.status_code != 400, f"Should not be rejected: {resp.data}"

    def test_exe_upload_blocked(self, admin_client):
        f = SimpleUploadedFile("virus.exe", b"MZ\x90\x00" + b"\x00" * 100, content_type="application/octet-stream")
        resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 400
        assert "extension" in resp.data.get("detail", "").lower()

    def test_disguised_exe_as_jpg_blocked(self, admin_client):
        """PE header inside a .jpg file — magic-byte check should catch it."""
        f = SimpleUploadedFile("photo.jpg", _PE_BYTES, content_type="image/jpeg")
        resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 400
        detail = resp.data.get("detail", "").lower()
        assert "rejected" in detail or "content" in detail or "extension" in detail

    def test_javascript_uri_in_pdf_blocked(self, admin_client):
        malicious = b"%PDF-1.7\n/JavaScript\n(eval('exploit'))"
        f = SimpleUploadedFile("doc.pdf", malicious, content_type="application/pdf")
        resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 400

    def test_unauthenticated_upload_rejected(self, api_client):
        f = SimpleUploadedFile("photo.jpg", _JPEG_BYTES, content_type="image/jpeg")
        resp = api_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 401

    def test_oversized_file_rejected(self, admin_client):
        # Patch the module-level constant (set at import time) rather than settings.
        with patch("apps.files.views._MAX_BYTES", 100):
            f = SimpleUploadedFile("photo.jpg", _JPEG_BYTES, content_type="image/jpeg")
            resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 400
        assert "size" in resp.data.get("detail", "").lower()

    def test_missing_file_returns_400(self, admin_client):
        resp = admin_client.post(UPLOAD_URL, {}, format="multipart")
        assert resp.status_code == 400
        assert "No file" in resp.data.get("detail", "")

    def test_php_extension_blocked(self, admin_client):
        f = SimpleUploadedFile("shell.php", b"<?php echo shell_exec($_GET['cmd']); ?>", content_type="text/plain")
        resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 400
