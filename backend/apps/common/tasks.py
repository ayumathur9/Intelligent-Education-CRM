"""
RECOVERY-001: Backup automation Celery tasks.

Performs scheduled PostgreSQL dumps, uploads to Supabase Storage,
enforces a 30-day retention policy, and logs the result.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.common.tasks.backup_database",
    ignore_result=False,
    soft_time_limit=300,
    time_limit=600,
)
def backup_database(self) -> dict:
    """
    RECOVERY-001: Dump the PostgreSQL database and upload to Supabase Storage.

    Triggered manually or via Celery beat (configure in CELERY_BEAT_SCHEDULE).
    Returns a status dict with the backup file path and size.
    """
    from django.conf import settings

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.error("backup_database: DATABASE_URL not set — cannot back up")
        return {"status": "error", "reason": "DATABASE_URL not configured"}

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"backup-{timestamp}.sql.gz"

    with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Run pg_dump and pipe through gzip.
        env = {**os.environ, "PGPASSWORD": _extract_pg_password(db_url)}
        cmd = ["pg_dump", "--no-owner", "--no-acl", db_url]
        gzip_cmd = ["gzip", "-c"]

        with open(tmp_path, "wb") as out_file:
            dump = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            gzip = subprocess.Popen(gzip_cmd, stdin=dump.stdout, stdout=out_file, stderr=subprocess.PIPE)
            dump.stdout.close()
            gzip.wait()
            dump.wait()

        if dump.returncode != 0:
            stderr = dump.stderr.read().decode()
            raise RuntimeError(f"pg_dump failed (exit {dump.returncode}): {stderr[:500]}")

        file_size = os.path.getsize(tmp_path)

        # Upload to Supabase Storage.
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            with open(tmp_path, "rb") as f:
                file_bytes = f.read()
            from apps.common.storage.supabase_storage import upload_file
            path, url = upload_file(
                folder="backups",
                filename=filename,
                file_bytes=file_bytes,
                content_type="application/gzip",
                make_unique=False,
            )
            logger.info("backup_database: uploaded %s (%d bytes) → %s", filename, file_size, url)
            result = {"status": "ok", "path": path, "size_bytes": file_size, "timestamp": timestamp}
        else:
            logger.warning("backup_database: Supabase not configured — backup saved locally only at %s", tmp_path)
            result = {"status": "local_only", "path": tmp_path, "size_bytes": file_size, "timestamp": timestamp}

    except Exception as exc:
        logger.error("backup_database FAILED: %s", exc)
        result = {"status": "error", "reason": str(exc)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return result


@shared_task(
    bind=True,
    name="apps.common.tasks.prune_old_backups",
    ignore_result=True,
    soft_time_limit=120,
    time_limit=240,
)
def prune_old_backups(self) -> None:
    """
    RECOVERY-001: Delete backup files older than 30 days from Supabase Storage.
    Keeps storage costs bounded and enforces retention policy.
    """
    from django.conf import settings
    from datetime import timedelta

    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        logger.debug("prune_old_backups: Supabase not configured, skipping")
        return

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)

    try:
        from supabase import create_client
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        bucket = settings.SUPABASE_STORAGE_BUCKET

        objects = client.storage.from_(bucket).list("backups")
        pruned = 0
        for obj in objects:
            name = obj.get("name", "")
            created_at_str = obj.get("created_at") or obj.get("updated_at", "")
            if created_at_str:
                try:
                    obj_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if obj_dt < cutoff:
                        client.storage.from_(bucket).remove([f"backups/{name}"])
                        pruned += 1
                        logger.info("prune_old_backups: deleted backups/%s", name)
                except (ValueError, TypeError):
                    pass

        logger.info("prune_old_backups: pruned %d old backup files", pruned)
    except Exception as exc:
        logger.error("prune_old_backups failed: %s", exc)


def _extract_pg_password(db_url: str) -> str:
    """Extract the password component from a postgres:// URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        return parsed.password or ""
    except Exception:
        return ""
