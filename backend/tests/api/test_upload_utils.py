"""
Tests for the centralized upload utility (CRIT-2).
"""
from __future__ import annotations

import io

import pytest
from django.test import override_settings

from apps.common.upload_utils import save_upload, _detect_mime


# ---------------------------------------------------------------------------
# _detect_mime unit tests
# ---------------------------------------------------------------------------

def test_detect_mime_jpeg():
    assert _detect_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 10, "photo.jpg") == "image/jpeg"


def test_detect_mime_png():
    assert _detect_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4, "img.png") == "image/png"


def test_detect_mime_pdf():
    assert _detect_mime(b"%PDF-1.4 content", "file.pdf") == "application/pdf"


def test_detect_mime_docx():
    assert _detect_mime(b"PK\x03\x04" + b"\x00" * 20, "report.docx") == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_detect_mime_fallback_to_filename():
    # Unknown bytes + recognizable filename extension.
    result = _detect_mime(b"random bytes here", "data.csv")
    assert "csv" in result or result == "text/csv"


# ---------------------------------------------------------------------------
# save_upload integration tests
# ---------------------------------------------------------------------------

class FakeUploadedFile:
    """Minimal mock of Django's UploadedFile."""
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self.size = len(content)

    def read(self) -> bytes:
        return self._content


@pytest.mark.django_db
@override_settings(
    MAX_UPLOAD_SIZE_BYTES=10 * 1024 * 1024,
    ALLOWED_UPLOAD_EXTENSIONS={"pdf", "jpg", "jpeg", "png", "docx"},
    ALLOWED_UPLOAD_MIME_TYPES={
        "application/pdf", "image/jpeg", "image/png",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    MEDIA_ROOT="/tmp/test_media",
)
def test_save_upload_rejects_empty_file():
    from rest_framework.exceptions import ValidationError
    f = FakeUploadedFile("test.pdf", b"")
    with pytest.raises(ValidationError, match="Empty"):
        save_upload(f)


@pytest.mark.django_db
@override_settings(
    MAX_UPLOAD_SIZE_BYTES=100,  # Very small limit
    ALLOWED_UPLOAD_EXTENSIONS={"pdf"},
    ALLOWED_UPLOAD_MIME_TYPES={"application/pdf"},
    MEDIA_ROOT="/tmp/test_media",
)
def test_save_upload_rejects_oversized_file():
    from rest_framework.exceptions import ValidationError
    content = b"%PDF-1.4 " + b"x" * 200
    f = FakeUploadedFile("large.pdf", content)
    with pytest.raises(ValidationError, match="exceeds"):
        save_upload(f)


@pytest.mark.django_db
@override_settings(
    MAX_UPLOAD_SIZE_BYTES=10 * 1024 * 1024,
    ALLOWED_UPLOAD_EXTENSIONS={"pdf"},
    ALLOWED_UPLOAD_MIME_TYPES={"application/pdf"},
    MEDIA_ROOT="/tmp/test_media",
)
def test_save_upload_rejects_disallowed_extension():
    from rest_framework.exceptions import ValidationError
    f = FakeUploadedFile("virus.exe", b"%PDF-1.4 content")
    with pytest.raises(ValidationError, match="extension"):
        save_upload(f)


@pytest.mark.django_db
@override_settings(
    MAX_UPLOAD_SIZE_BYTES=10 * 1024 * 1024,
    ALLOWED_UPLOAD_EXTENSIONS={"pdf"},
    ALLOWED_UPLOAD_MIME_TYPES={"application/pdf"},
    MEDIA_ROOT="/tmp/test_media",
)
def test_save_upload_rejects_mime_extension_mismatch():
    """A JPEG pretending to be a PDF should be rejected."""
    from rest_framework.exceptions import ValidationError
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    f = FakeUploadedFile("fake.pdf", jpeg_bytes)
    with pytest.raises(ValidationError):
        save_upload(f)
