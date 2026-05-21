"""
Supabase Storage service layer — CRIT-003.

All production file I/O goes through this module; the local filesystem is
only used in development (no SUPABASE_URL configured).

Public API:
  upload_file()     — upload bytes to a bucket (retry-safe, unique naming)
  delete_file()     — remove a file from a bucket (never raises)
  get_public_url()  — CDN URL for public buckets
  get_signed_url()  — time-limited URL for private/restricted files
  supabase_healthy()— liveness probe for the health endpoint
"""
from __future__ import annotations

import logging
import time
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.5  # seconds between upload retries


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _client():
    from apps.common.supabase_client import get_supabase_client
    return get_supabase_client()


def _resolve_bucket(bucket: str | None) -> str:
    return bucket or getattr(settings, "SUPABASE_STORAGE_BUCKET", "crm-uploads")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_file(
    *,
    folder: str,
    filename: str | None = None,
    file_bytes: bytes,
    content_type: str,
    bucket: str | None = None,
    make_unique: bool = True,
) -> tuple[str, str]:
    """
    Upload *file_bytes* to Supabase Storage.

    Returns ``(path, public_url)``.
    Raises ``RuntimeError`` if all retry attempts are exhausted.

    Args:
        folder:       Storage folder prefix, e.g. ``"uploads"`` or ``"avatars"``.
        filename:     Original filename; used to preserve the extension.
        file_bytes:   Raw file content.
        content_type: MIME type string.
        bucket:       Override SUPABASE_STORAGE_BUCKET setting.
        make_unique:  Prepend a UUID4 so collisions are impossible.
    """
    resolved_bucket = _resolve_bucket(bucket)

    # Build a collision-safe storage path.
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
    else:
        ext = ""

    if make_unique:
        safe_name = f"{uuid.uuid4()}.{ext}" if ext else str(uuid.uuid4())
    else:
        safe_name = filename or str(uuid.uuid4())

    path = f"{folder}/{safe_name}"

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            client = _client()
            client.storage.from_(resolved_bucket).upload(
                path,
                file_bytes,
                file_options={"content-type": content_type, "upsert": "false"},
            )
            break  # success
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Supabase upload attempt %d/%d failed for %s: %s",
                attempt,
                _MAX_RETRIES,
                path,
                exc,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
    else:
        raise RuntimeError(
            f"Supabase upload failed for {path!r} after {_MAX_RETRIES} attempts: {last_exc}"
        )

    public_url = get_public_url(bucket=resolved_bucket, path=path)
    logger.info("Uploaded %s → Supabase bucket=%s", path, resolved_bucket)
    return path, public_url


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_file(*, bucket: str | None = None, path: str) -> bool:
    """
    Remove *path* from Supabase Storage.

    Returns ``True`` on success. Never raises — failures are logged at ERROR.
    """
    resolved_bucket = _resolve_bucket(bucket)
    try:
        client = _client()
        client.storage.from_(resolved_bucket).remove([path])
        logger.info("Deleted Supabase file %s from bucket %s", path, resolved_bucket)
        return True
    except Exception as exc:
        logger.error(
            "Failed to delete Supabase file %s from bucket %s: %s",
            path,
            resolved_bucket,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def get_public_url(*, bucket: str | None = None, path: str) -> str:
    """Return the public CDN URL for *path*."""
    resolved_bucket = _resolve_bucket(bucket)
    try:
        client = _client()
        result = client.storage.from_(resolved_bucket).get_public_url(path)
        # supabase-py ≥2.0 returns the URL directly as a string.
        return result if isinstance(result, str) else result.get("publicUrl", "")
    except Exception as exc:
        logger.error("get_public_url failed for %s: %s", path, exc)
        # Graceful fallback: construct URL manually from base setting.
        base = getattr(settings, "SUPABASE_PUBLIC_URL_BASE", "").rstrip("/")
        return f"{base}/storage/v1/object/public/{resolved_bucket}/{path}"


def get_signed_url(
    *,
    bucket: str | None = None,
    path: str,
    expires_in: int = 3600,
) -> str:
    """
    Return a time-limited signed URL for *path*.

    Args:
        expires_in: Lifetime in seconds (default 1 hour).
    """
    resolved_bucket = _resolve_bucket(bucket)
    try:
        client = _client()
        result = client.storage.from_(resolved_bucket).create_signed_url(path, expires_in)
        # supabase-py ≥2.0 returns {"signedURL": "..."} or {"signedUrl": "..."}.
        if isinstance(result, dict):
            return result.get("signedURL") or result.get("signedUrl") or ""
        return str(result)
    except Exception as exc:
        logger.error("get_signed_url failed for %s: %s", path, exc)
        return ""


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------

def supabase_healthy() -> bool:
    """
    Lightweight liveness check — used by the health endpoint.

    Verifies that the Supabase client can list storage buckets.
    Returns ``False`` (never raises) if Supabase is unreachable or not configured.
    """
    if not getattr(settings, "SUPABASE_URL", "") or not getattr(
        settings, "SUPABASE_SERVICE_ROLE_KEY", ""
    ):
        return False
    try:
        _client().storage.list_buckets()
        return True
    except Exception as exc:
        logger.warning("Supabase health check failed: %s", exc)
        return False
