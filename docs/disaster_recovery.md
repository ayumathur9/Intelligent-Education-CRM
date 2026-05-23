# Disaster Recovery Playbook

> **Intelligent Education CRM — RECOVERY-001/002**
> Last updated: 2026-05-22
> Owner: Platform Engineering

---

## 1. Database Failure

### 1a. RDS / Railway PostgreSQL is down

**Symptoms:** API returns 500 or connection timeout errors; health endpoint reports `"database": "error"`.

**Steps:**

1. **Verify the database is actually down:**
   ```bash
   railway run python manage.py dbshell
   ```

2. **Railway auto-restarts** the PostgreSQL plugin. Wait 2–5 minutes and check the Railway dashboard.

3. **If data corruption:** restore from the latest backup (see Section 2).

4. **Force a Railway redeploy** after DB is back:
   ```bash
   railway up
   ```

---

## 2. Restore Database from Backup

Automated nightly backups are stored in Supabase Storage under the `backups/` folder with filenames like `backup-20260522T020000Z.sql.gz`.

### 2a. Download and restore latest backup

```bash
# Download from Supabase Storage (requires supabase CLI or SUPABASE_SERVICE_ROLE_KEY)
python scripts/restore_backup.py --latest

# Or manually:
# 1. Download backup-<TIMESTAMP>.sql.gz from Supabase Storage
# 2. Decompress and restore:
gunzip -c backup-<TIMESTAMP>.sql.gz | psql "$DATABASE_URL"
```

### 2b. Verify after restore

```bash
python manage.py migrate --check
python manage.py check
curl https://your-project.railway.app/api/health/
```

---

## 3. Redis Failure

**Symptoms:** WebSocket connections fail; cache misses flood the DB; throttle logs stop.

**Steps:**

1. Railway Redis auto-restarts. Wait 60 seconds.

2. **Redis data is ephemeral by design.** The application is stateless relative to Redis:
   - Cache keys repopulate on next DB query (within TTL window).
   - WebSocket channel groups are re-established on client reconnect.
   - JWT blacklist is in PostgreSQL — not Redis. Not affected.
   - Celery task queue is backed by Redis. Pending tasks are lost. See Section 4.

3. **If Redis is persistently unavailable**, the application degrades gracefully:
   - Django falls back to `LocMemCache` (in-process, single-worker).
   - WebSocket broadcasting only works within a single worker process.

---

## 4. Celery Worker Failure

**Symptoms:** Emails not sent; file cleanup not running; audit logs not being written.

**Steps:**

1. Check Railway logs for the `celery-worker` service.

2. Restart the Celery worker:
   ```bash
   railway service restart celery-worker
   ```

3. **Lost tasks** (tasks in the Redis queue when Redis went down):
   - Email-on-registration: user can request a password-reset email to self-verify.
   - Password-reset emails: user can retry via the password reset form.
   - Audit events: minor — not mission-critical for operations.

4. **Run missed beat tasks manually:**
   ```bash
   railway run celery -A config.celery call apps.users.tasks.purge_expired_tokens
   railway run celery -A config.celery call apps.common.tasks.backup_database
   ```

---

## 5. Supabase Storage Failure

**Symptoms:** File uploads fail with 5xx; health endpoint reports `"storage": "error"`.

**Steps:**

1. Check the Supabase status page.

2. The application falls back to **local filesystem in development**. In production, uploads will fail until Supabase recovers.

3. **Re-upload orphaned files** after Supabase recovers:
   ```bash
   railway run python manage.py shell -c "
   from apps.files.tasks import cleanup_orphaned_files
   cleanup_orphaned_files.delay()
   "
   ```

---

## 6. Secret Rotation

See [incident_recovery.md](incident_recovery.md) for the full secret rotation procedure.

**Quick reference:**

| Secret | Rotation Command |
|---|---|
| `DJANGO_SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `FIELD_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **WARNING: rotating this key invalidates all encrypted PII fields** |
| `SUPABASE_SERVICE_ROLE_KEY` | Rotate in Supabase dashboard → Settings → API |
| JWT blacklist | Run `python manage.py flushexpiredtokens` to clear all outstanding tokens (forces re-login) |

---

## 7. Full Application Recovery Checklist

Run this checklist after any major incident before declaring recovery complete:

- [ ] `GET /api/health/` returns HTTP 200 with all checks green
- [ ] Can log in via `/api/auth/login/`
- [ ] Can list students via `/api/students/`
- [ ] Can upload a file
- [ ] WebSocket notification appears in UI
- [ ] Celery worker is processing tasks (`celery inspect active`)
- [ ] No `ERROR`-level entries in Railway logs for > 5 minutes
- [ ] Sentry shows error rate returning to baseline

---

## 8. Restore Script

```python
# scripts/restore_backup.py
"""Download and restore the latest database backup from Supabase Storage."""
import os
import subprocess
import sys
from urllib.parse import urlparse

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

def latest_backup():
    from supabase import create_client
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    objects = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).list("backups")
    objects.sort(key=lambda o: o.get("created_at", ""), reverse=True)
    return objects[0]["name"] if objects else None

name = latest_backup()
if not name:
    print("No backups found.")
    sys.exit(1)

print(f"Restoring: {name}")
# Download and pipe to psql
from supabase import create_client
client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
data = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(f"backups/{name}")

import gzip, io
with gzip.open(io.BytesIO(data)) as f:
    sql = f.read()

proc = subprocess.run(
    ["psql", os.getenv("DATABASE_URL", "")],
    input=sql,
    capture_output=True,
)
if proc.returncode != 0:
    print("Restore FAILED:", proc.stderr.decode())
    sys.exit(1)
print("Restore complete.")
```
