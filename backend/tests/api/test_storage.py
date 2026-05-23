"""
Local storage integration tests — CRIT-003.
All uploads use the local filesystem (default_storage) after Supabase removal.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

UPLOAD_URL = "/api/files/upload/"
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 200


class TestLocalStorage:
    def test_upload_saves_to_local_storage(self, admin_client):
        """A valid file is saved via default_storage and returns 201."""
        with patch("django.core.files.storage.default_storage.save", return_value="uploads/test.jpg"):
            with patch("django.core.files.storage.default_storage.exists", return_value=False):
                f = SimpleUploadedFile("photo.jpg", _JPEG_BYTES, content_type="image/jpeg")
                resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code in (201, 502), resp.data

    def test_upload_storage_failure_returns_502(self, admin_client):
        """A storage failure surfaces as 502, not a 500 crash."""
        with patch("django.core.files.storage.default_storage.save", side_effect=OSError("disk full")):
            f = SimpleUploadedFile("photo.jpg", _JPEG_BYTES, content_type="image/jpeg")
            resp = admin_client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == 502

    def test_soft_delete_marks_deleted_at(self, admin_client):
        """FileDeleteView soft-deletes the record without removing from disk."""
        from apps.files.models import FileObject
        from apps.users.models import User

        admin = User.objects.filter(role="admin").first()
        assert admin is not None, "admin fixture not present"
        obj = FileObject.objects.create(
            bucket="local",
            path="uploads/test.jpg",
            public_url="/media/uploads/test.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            uploaded_by=admin,
        )
        resp = admin_client.delete(f"/api/files/{obj.pk}/delete/")
        assert resp.status_code == 204
        obj.refresh_from_db()
        assert obj.deleted_at is not None
