"""Celery tasks for the files app — ASYNC-002."""
from __future__ import annotations

import logging

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
    If a threat is found, soft-delete the record and remove from Supabase.
    """
    from apps.files.models import FileObject
    from apps.common.security.file_scanner import scan_file
    from django.utils import timezone

    try:
        file_obj = FileObject.objects.get(pk=file_id, deleted_at__isnull=True)
    except FileObject.DoesNotExist:
        logger.warning("async_malware_scan: file %s not found or already deleted", file_id)
        return {"status": "not_found"}

    if not file_obj.public_url:
        return {"status": "no_url"}

    # Download the file for scanning.
    try:
        import requests
        resp = requests.get(file_obj.public_url, timeout=30)
        resp.raise_for_status()
        file_bytes = resp.content
    except Exception as exc:
        logger.warning("async_malware_scan: could not download file %s — %s", file_id, exc)
        return {"status": "download_failed"}

    filename = file_obj.path.split("/")[-1] if file_obj.path else "unknown"
    result = scan_file(file_bytes=file_bytes, filename=filename)

    if not result.safe:
        logger.warning(
            "async_malware_scan: THREAT detected in file %s — %s",
            file_id,
            result.reason,
        )
        # Soft-delete.
        file_obj.deleted_at = timezone.now()
        file_obj.save(update_fields=["deleted_at"])

        # Remove from Supabase storage.
        if file_obj.path:
            try:
                from apps.common.storage.supabase_storage import delete_file
                delete_file(path=file_obj.path)
            except Exception:
                pass

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
    Every 4 hours: remove Supabase objects that have no matching FileObject record.
    Prevents orphaned files from accumulating after failed transactions.
    """
    from django.conf import settings
    from apps.files.models import FileObject

    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        logger.debug("cleanup_orphaned_files: Supabase not configured, skipping")
        return

    try:
        from supabase import create_client
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        bucket = settings.SUPABASE_STORAGE_BUCKET

        known_paths = set(
            FileObject.objects.filter(deleted_at__isnull=True).values_list("path", flat=True)
        )

        orphan_count = 0
        for folder in ("student-documents", "school-documents", "profiles"):
            try:
                objects = client.storage.from_(bucket).list(folder)
            except Exception as exc:
                logger.warning("cleanup_orphaned_files: list %s failed — %s", folder, exc)
                continue

            for obj in objects:
                path = f"{folder}/{obj.get('name', '')}"
                if path not in known_paths:
                    try:
                        client.storage.from_(bucket).remove([path])
                        orphan_count += 1
                    except Exception as exc:
                        logger.warning("cleanup_orphaned_files: delete %s failed — %s", path, exc)

        logger.info("cleanup_orphaned_files: removed %d orphaned files", orphan_count)
    except Exception as exc:
        logger.error("cleanup_orphaned_files failed: %s", exc)
