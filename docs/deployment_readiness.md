# Deployment Readiness Guide
> Covers Railway deployment, environment variables, infrastructure, and pre-launch validation.

---

## Required Railway Environment Variables

Set these in Railway → Your Service → Variables before every production deploy.

### Mandatory (Deploy will fail or be insecure without these)

```env
# Django core
DJANGO_SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DJANGO_DEBUG=0
DJANGO_ENV=production
DJANGO_ALLOWED_HOSTS=your-project.railway.app,your-custom-domain.com
DJANGO_CORS_ALLOWED_ORIGINS=https://your-project.railway.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-project.railway.app

# Database (auto-injected by Railway PostgreSQL plugin)
DATABASE_URL=postgresql://...

# Supabase (regenerate after CRIT-001 remediation)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=<new anon key from Supabase dashboard>
SUPABASE_SERVICE_ROLE_KEY=<new service role key from Supabase dashboard>
SUPABASE_STORAGE_BUCKET=crm-uploads

# Email (regenerate Gmail app password)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=contact.intelligenteducation@gmail.com
EMAIL_HOST_PASSWORD=<new Gmail app password>
DEFAULT_FROM_EMAIL=Intelligent Education <contact.intelligenteducation@gmail.com>
FRONTEND_BASE_URL=https://your-project.railway.app
```

### Recommended (Infrastructure)

```env
# Redis (add Redis plugin to Railway project first)
REDIS_URL=redis://...  # auto-set by Railway Redis plugin

# JWT lifetimes (defaults are fine, override if needed)
JWT_ACCESS_TOKEN_MINUTES=15
JWT_REFRESH_TOKEN_DAYS=7

# Rate limits (DRF throttle overrides)
DRF_LOGIN_RATE=5/min
DRF_PASSWORD_RESET_RATE=3/min

# Security
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SECURE_HSTS_SECONDS=31536000

# File uploads
MAX_UPLOAD_SIZE_MB=10
```

### Superuser Bootstrap (one-time, remove after first deploy)

```env
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=<strong unique password>
```

---

## Railway Deployment Steps

### First Deploy

1. Create a new Railway project
2. Add **PostgreSQL** plugin → Railway will set `DATABASE_URL`
3. Add **Redis** plugin → Railway will set `REDIS_URL`
4. Connect your GitHub repository
5. Set all mandatory environment variables (table above)
6. Set build command: *(none needed — Dockerfile handles it)*
7. Set start command: `./backend/start.sh` *(or Dockerfile CMD)*
8. Deploy

### Subsequent Deploys

1. Verify no new required env vars introduced
2. Push to `main` branch → Railway auto-deploys
3. Monitor logs for migration errors
4. Run health check: `curl https://your-domain/api/health/`

---

## Pre-Deploy Validation Commands

Run locally before every production deployment:

```bash
# Django deployment check
cd backend
python manage.py check --deploy

# Security scan
pip install bandit
bandit -r apps/ -ll

# Dependency vulnerability check
pip install pip-audit
pip-audit

# Run tests
python -m pytest tests/ -v --tb=short

# Verify migrations are up to date
python manage.py showmigrations | grep '\[ \]'
```

---

## Infrastructure Components

| Component | Provider | Status | Notes |
|---|---|---|---|
| Web server (ASGI) | Daphne 4.x on Railway | ✅ Configured | Single worker — needs Redis for scale |
| Database | PostgreSQL on Railway | ✅ Configured | Add backup strategy |
| Channel layer | In-memory → **Redis** | ❌ Needs CRIT-002 fix | Must be Redis for production |
| File storage | Local fs → **Supabase** | ❌ Needs CRIT-003 fix | Ephemeral on Railway |
| Cache | None → **Redis** | ❌ Needs INFRA-003 fix | Dashboard hitting DB every load |
| Task queue | None → **Celery** | ⚠️ Future | Email is synchronous |
| Error tracking | None → **Sentry** | ❌ Needs LOW-011 | No error visibility |
| Log aggregation | Railway logs (basic) | ⚠️ Partial | Needs structured JSON |
| Health monitoring | None | ❌ Needs HIGH-006 | No uptime alerting |

---

## Database Backup Strategy

### Option A — Railway Backup (Paid)
Railway Pro plan includes automatic daily backups.
Enable in: Railway → PostgreSQL plugin → Backup settings.

### Option B — Manual pg_dump (Free tier)
Add to Railway cron or external scheduler:

```bash
#!/bin/bash
# backup.sh — run daily
BACKUP_FILE="crm-backup-$(date +%Y%m%d-%H%M%S).sql.gz"
pg_dump $DATABASE_URL | gzip > /tmp/$BACKUP_FILE

# Upload to Supabase Storage
# (requires supabase CLI or curl)
```

### Option C — Supabase as backup target
Use Supabase Storage to store pg_dump files — provides versioned, durable object storage.

### Restore Procedure

```bash
# Download backup
# Restore to new database
psql $DATABASE_URL < backup.sql
```

---

## Rollback Procedure

### Application Rollback

Railway keeps a deployment history. To rollback:
1. Railway Dashboard → Your Service → Deployments
2. Find the last working deployment
3. Click → **Redeploy**

### Database Rollback (Migration)

```bash
# Identify target migration
python manage.py showmigrations

# Roll back specific app to migration N
python manage.py migrate <app_name> <migration_name>

# Example: roll back crm to 0003
python manage.py migrate crm 0003_previous_migration
```

> **Warning:** Destructive migrations (column drops) cannot be rolled back without data loss.
> Always use phased migrations (add nullable → backfill → enforce constraint).

---

## Production Monitoring

### Health Check Endpoint
After HIGH-006 is implemented:
```
GET /api/health/
Response: {"status": "ok", "db": true, "redis": true}
```

### Recommended Monitoring Stack
- **Uptime Robot** (free) — ping `/api/health/` every 5 minutes
- **Railway Metrics** — CPU/memory/request count built-in
- **Sentry** — error tracking and alerting
- **Railway Logs** — structured JSON logs via `python-json-logger`

---

## Secret Rotation Procedure

When credentials are compromised (execute in this order):

### 1. Supabase Keys
```
Supabase Dashboard → Project Settings → API → Regenerate keys
```
Update Railway env vars: `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

### 2. Gmail App Password
```
Google Account → Security → 2-Step Verification → App passwords → Revoke CRM
Create new app password
```
Update Railway env var: `EMAIL_HOST_PASSWORD`

### 3. Django SECRET_KEY
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Update Railway env var: `DJANGO_SECRET_KEY`
**Warning:** Rotating SECRET_KEY invalidates all existing sessions and JWT tokens.
Users will be logged out. Do during maintenance window.

### 4. Database Password
Via Railway PostgreSQL settings or Supabase dashboard.
Update `DATABASE_URL` in Railway env vars.
