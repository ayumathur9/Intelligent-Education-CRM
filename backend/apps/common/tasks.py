"""
RECOVERY-001: Backup automation Celery tasks.

Performs scheduled PostgreSQL dumps to the local BACKUP_ROOT directory
and enforces a configurable retention policy (default 30 days).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


def _backup_dir() -> Path:
    """Return the backup directory path, creating it if necessary."""
    from django.conf import settings
    backup_root = Path(getattr(settings, "BACKUP_ROOT", Path(__file__).resolve().parent.parent.parent / "backups"))
    backup_root.mkdir(parents=True, exist_ok=True)
    return backup_root


@shared_task(
    bind=True,
    name="apps.common.tasks.backup_database",
    ignore_result=False,
    soft_time_limit=300,
    time_limit=600,
)
def backup_database(self) -> dict:
    """
    RECOVERY-001: Dump the PostgreSQL database to a local gzip file.

    Output: BACKUP_ROOT/backup-<timestamp>.sql.gz
    Returns a status dict with the backup file path and size.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.error("backup_database: DATABASE_URL not set — cannot back up")
        return {"status": "error", "reason": "DATABASE_URL not configured"}

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"backup-{timestamp}.sql.gz"
    backup_dir = _backup_dir()
    out_path = backup_dir / filename

    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        # CRIT-4: Pass credentials via environment, not on the command line.
        # Build a clean DSN without the password for pg_dump --dbname argument.
        pg_env = {
            **os.environ,
            "PGPASSWORD": parsed.password or "",
            "PGSSLMODE": "require",
        }
        pg_args = [
            "pg_dump",
            "--no-owner",
            "--no-acl",
            "--format=plain",
            f"--host={parsed.hostname}",
            f"--port={parsed.port or 5432}",
            f"--username={parsed.username or 'postgres'}",
            parsed.path.lstrip("/"),  # database name
        ]

        # CRIT-4: Use context manager so the output file is always closed.
        with open(out_path, "wb") as f_out:
            dump = subprocess.Popen(
                pg_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=pg_env,
            )
            gzip_proc = subprocess.Popen(
                ["gzip", "-c"],
                stdin=dump.stdout,
                stdout=f_out,
                stderr=subprocess.PIPE,
            )
            dump.stdout.close()  # Allow dump to receive SIGPIPE if gzip exits.
            gzip_proc.wait()
            dump.wait()

        if dump.returncode != 0:
            stderr_out = dump.stderr.read().decode(errors="replace")
            raise RuntimeError(f"pg_dump failed (exit {dump.returncode}): {stderr_out[:500]}")

        file_size = out_path.stat().st_size
        logger.info("backup_database: saved %s (%d bytes)", out_path, file_size)
        return {"status": "ok", "path": str(out_path), "size_bytes": file_size, "timestamp": timestamp}

    except Exception as exc:
        logger.error("backup_database FAILED: %s", exc)
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        # Alert admins of backup failure.
        try:
            from apps.common.email_service import send_backup_failure_alert
            send_backup_failure_alert(str(exc))
        except Exception:
            pass
        return {"status": "error", "reason": str(exc)}


@shared_task(
    bind=True,
    name="apps.common.tasks.prune_old_backups",
    ignore_result=True,
    soft_time_limit=120,
    time_limit=240,
)
def prune_old_backups(self) -> None:
    """
    RECOVERY-001: Delete local backup files older than BACKUP_RETENTION_DAYS.
    Prevents unbounded disk usage and enforces the retention policy.
    """
    from django.conf import settings
    retention_days = int(getattr(settings, "BACKUP_RETENTION_DAYS", 30))
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    backup_dir = _backup_dir()

    pruned = 0
    for f in backup_dir.glob("backup-*.sql.gz"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                pruned += 1
                logger.info("prune_old_backups: deleted %s", f.name)
        except Exception as exc:
            logger.warning("prune_old_backups: could not process %s — %s", f, exc)

    logger.info("prune_old_backups: pruned %d old backup files", pruned)


@shared_task(
    bind=True,
    name="apps.common.tasks.send_weekly_profile_reminders",
    ignore_result=True,
    soft_time_limit=600,
    time_limit=900,
)
def send_weekly_profile_reminders(self) -> None:
    """
    Weekly Celery task: send profile-completion reminder emails to all active students
    who have incomplete required sections. Runs every 7 days via beat schedule.
    Skips students whose profiles are fully complete (N/A fields count as filled).
    """
    from apps.common.management.commands.send_profile_reminders import (
        _missing_sections,
        _send_reminder,
    )
    from apps.crm.models import Student

    students = (
        Student.objects.filter(is_active=True)
        .exclude(email="")
        .prefetch_related("education_history")
        .select_related("course")
    )

    sent = skipped = errors = 0
    for student in students:
        missing = _missing_sections(student)
        if not missing:
            skipped += 1
            continue
        try:
            _send_reminder(student, missing, dry_run=False)
            sent += 1
        except Exception as exc:
            errors += 1
            logger.warning("send_weekly_profile_reminders: failed for %s — %s", student.student_code, exc)

    logger.info(
        "send_weekly_profile_reminders: sent=%d skipped=%d errors=%d",
        sent, skipped, errors,
    )


def _extract_pg_password(db_url: str) -> str:
    """Extract the password component from a postgres:// URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        return parsed.password or ""
    except Exception:
        return ""
