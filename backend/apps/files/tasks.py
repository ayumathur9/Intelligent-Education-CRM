"""Celery tasks for the files app — ASYNC-002."""
from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.files.tasks.async_malware_scan",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 30},
    soft_time_limit=120,
    time_limit=180,
)
def async_malware_scan(self, file_id: int) -> dict:
    """
    Run the full malware scan pipeline on an already-uploaded FileObject.
    Reads the file from local MEDIA_ROOT. If a threat is found, soft-deletes
    the DB record and removes the file from disk.
    """
    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.utils import timezone
    from apps.files.models import FileObject
    from apps.common.security.file_scanner import scan_file

    try:
        file_obj = FileObject.objects.get(pk=file_id, deleted_at__isnull=True)
    except FileObject.DoesNotExist:
        logger.warning("async_malware_scan: file %s not found or already deleted", file_id)
        return {"status": "not_found"}

    if not file_obj.path:
        return {"status": "no_path"}

    try:
        with default_storage.open(file_obj.path, "rb") as f:
            file_bytes = f.read()
    except Exception as exc:
        logger.warning("async_malware_scan: could not read file %s — %s", file_id, exc)
        return {"status": "read_failed"}

    filename = Path(file_obj.path).name
    result = scan_file(file_bytes=file_bytes, filename=filename)

    if not result.safe:
        logger.warning(
            "async_malware_scan: THREAT detected in file %s — %s",
            file_id,
            result.reason,
        )
        file_obj.deleted_at = timezone.now()
        file_obj.save(update_fields=["deleted_at"])

        try:
            default_storage.delete(file_obj.path)
        except Exception as exc:
            logger.warning("async_malware_scan: could not delete file %s from storage — %s", file_id, exc)

        return {"status": "deleted", "reason": result.reason, "flags": result.flags}

    logger.debug("async_malware_scan: file %s is clean", file_id)
    return {"status": "clean"}


@shared_task(
    bind=True,
    name="apps.files.tasks.cleanup_orphaned_files",
    ignore_result=True,
    soft_time_limit=300,
    time_limit=600,
)
def cleanup_orphaned_files(self) -> None:
    """
    LOW: Delete physical files on disk that have no corresponding FileObject record
    (or whose FileObject has been soft-deleted for more than ORPHAN_FILE_RETENTION_DAYS days).

    Runs weekly — safe to run on any schedule since it only touches the upload folder.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.utils import timezone

    from apps.files.models import FileObject

    retention_days = int(getattr(settings, "ORPHAN_FILE_RETENTION_DAYS", 7))
    cutoff = timezone.now() - timedelta(days=retention_days)

    # Collect all paths tracked in the DB (both active and soft-deleted).
    known_paths: set[str] = set(
        FileObject.objects.values_list("path", flat=True)
    )
    soft_deleted_old: set[str] = set(
        FileObject.objects.filter(deleted_at__lt=cutoff).values_list("path", flat=True)
    )

    media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
    upload_dir = media_root / "uploads"
    if not upload_dir.exists():
        return

    removed = 0
    for file_path in upload_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(media_root).as_posix()
        if rel_path not in known_paths or rel_path in soft_deleted_old:
            try:
                default_storage.delete(rel_path)
                removed += 1
                logger.info("cleanup_orphaned_files: removed %s", rel_path)
            except Exception as exc:
                logger.warning("cleanup_orphaned_files: could not remove %s — %s", rel_path, exc)

    # Remove FileObject records for old soft-deleted entries to keep the table tidy.
    deleted_count, _ = FileObject.objects.filter(deleted_at__lt=cutoff).delete()
    logger.info(
        "cleanup_orphaned_files: removed %d physical files, purged %d DB records",
        removed,
        deleted_count,
    )
