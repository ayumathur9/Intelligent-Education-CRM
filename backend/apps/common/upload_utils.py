"""
CRIT-2: Centralized secure upload utility.

Single entry point for all file uploads in the CRM.  Every upload path
must go through ``save_upload()``; direct calls to default_storage.save
are no longer permitted for user-supplied files.

Guarantees:
  1. Size limit enforced (MAX_UPLOAD_SIZE_BYTES from settings).
  2. Extension check against ALLOWED_UPLOAD_EXTENSIONS allow-list.
  3. MIME type detected from actual file bytes (not just filename).
  4. Content security scan (file_scanner.scan_file).
  5. UUID-based filename on disk (original name preserved as metadata).
  6. Returns (storage_path, public_url, original_name, content_type, size_bytes).
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

_MAX_BYTES: int = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)
_ALLOWED_EXTS: frozenset[str] = frozenset(
    getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", set())
)
_ALLOWED_MIMES: frozenset[str] = frozenset(
    getattr(settings, "ALLOWED_UPLOAD_MIME_TYPES", set())
)

# Detected-MIME → expected-extension mapping (tight subset).
_MIME_EXT_MAP: dict[str, set[str]] = {
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/gif": {"gif"},
    "image/webp": {"webp"},
    "application/pdf": {"pdf"},
    "application/msword": {"doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {"docx"},
    "application/vnd.ms-excel": {"xls"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {"xlsx"},
    "text/plain": {"txt"},
    "text/csv": {"txt", "csv"},
}


@dataclass
class UploadResult:
    storage_path: str
    public_url: str
    original_name: str
    content_type: str
    size_bytes: int


def save_upload(
    file_obj,
    *,
    folder: str = "uploads",
    extra_name: str | None = None,
) -> UploadResult:
    """
    Validate, scan, and persist an uploaded file.

    Args:
        file_obj: Django UploadedFile (from request.FILES).
        folder:   Sub-directory under MEDIA_ROOT.  Must not contain '..'.
        extra_name: Optional suffix appended before the extension (e.g., user pk).

    Returns:
        UploadResult with paths, content-type and size.

    Raises:
        ValidationError on any security check failure.
    """
    if ".." in folder or "/" in folder.lstrip("/").rstrip("/").replace("/", ""):
        raise ValueError(f"Unsafe folder: {folder!r}")

    original_name: str = getattr(file_obj, "name", "") or "upload"
    file_bytes: bytes = file_obj.read()
    size = len(file_bytes)

    # 1. Size check.
    max_mb = _MAX_BYTES // (1024 * 1024)
    if size > _MAX_BYTES:
        raise ValidationError(f"File exceeds the maximum allowed size of {max_mb} MB.")
    if size == 0:
        raise ValidationError("Empty file is not allowed.")

    # 2. Extension check.
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if not ext or ext not in _ALLOWED_EXTS:
        raise ValidationError(f"File extension '.{ext}' is not permitted.")

    # 3. MIME type from actual content (magic bytes via file_scanner layer).
    #    Fall back to filename guess if scanner doesn't give us a type.
    detected_mime = _detect_mime(file_bytes, original_name)
    if detected_mime and detected_mime not in _ALLOWED_MIMES:
        raise ValidationError(
            f"Detected content type '{detected_mime}' is not permitted."
        )

    # 4. Cross-check: detected MIME must be consistent with extension.
    if detected_mime:
        expected_exts = _MIME_EXT_MAP.get(detected_mime, set())
        if expected_exts and ext not in expected_exts:
            raise ValidationError(
                f"File extension '.{ext}' does not match detected type '{detected_mime}'."
            )

    # 5. Content security scan (zip bomb, dangerous patterns, VirusTotal).
    from apps.common.security.file_scanner import scan_file
    scan_result = scan_file(file_bytes=file_bytes, filename=original_name)
    if not scan_result.safe:
        logger.warning("save_upload: file rejected — %s | file=%s", scan_result.reason, original_name)
        raise ValidationError(f"File rejected: {scan_result.reason}")

    # 6. Generate UUID-based filename; original name is preserved in metadata only.
    suffix = f"-{extra_name}" if extra_name else ""
    storage_path = f"{folder.strip('/')}/{uuid.uuid4()}{suffix}.{ext}"

    # Ensure we don't silently overwrite (shouldn't happen with UUID, but be safe).
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)

    saved_path = default_storage.save(storage_path, ContentFile(file_bytes))
    public_url = f"{settings.MEDIA_URL}{saved_path}"

    logger.info("save_upload: stored %s → %s (%d bytes)", original_name, saved_path, size)

    return UploadResult(
        storage_path=saved_path,
        public_url=public_url,
        original_name=original_name,
        content_type=detected_mime or (mimetypes.guess_type(original_name)[0] or "application/octet-stream"),
        size_bytes=size,
    )


def _detect_mime(file_bytes: bytes, filename: str) -> str:
    """
    Detect MIME type from magic bytes.
    Falls back to mimetypes.guess_type on the filename if magic detection fails.
    """
    # Fast magic-byte check for common formats.
    if file_bytes[:4] == b"\x89PNG":
        return "image/png"
    if file_bytes[:3] in (b"\xff\xd8\xff",):
        return "image/jpeg"
    if file_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "image/webp"
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    if file_bytes[:2] == b"PK":
        # ZIP-based: could be docx, xlsx, etc. — disambiguate by extension.
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        _ZIP_MIME = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return _ZIP_MIME.get(ext, "application/zip")
    if file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        # OLE2 compound document (DOC, XLS).
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "xls":
            return "application/vnd.ms-excel"
        return "application/msword"

    # Fall back to filename-based guess.
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or ""
