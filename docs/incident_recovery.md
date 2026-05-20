# Incident Recovery & Response Guide

---

## 1. Compromised Credentials Response

**Trigger:** Supabase keys, Gmail password, or DB password exposed.

### Immediate Steps (execute within 15 minutes)

```bash
# Step 1: Assess exposure
# Check git log for committed .env
git log --all --full-history -- "**/.env"
git log --all --full-history -- ".env"

# Step 2: Revoke in order of risk
# a) Supabase: Dashboard → Project Settings → API → Regenerate
# b) Gmail: Google Account → Security → App Passwords → Revoke
# c) DB: Railway → PostgreSQL → Reset Password / Supabase → Database → Reset

# Step 3: Update Railway env vars with new credentials
# Step 4: Redeploy to pick up new env vars

# Step 5: If committed to git, purge history
pip install git-filter-repo
git filter-repo --path backend/.env --invert-paths
git push --force-with-lease origin main
```

### Post-Incident
- [ ] Review Railway access logs for suspicious activity
- [ ] Review Supabase audit logs
- [ ] Check Google account for unauthorized access
- [ ] Notify affected users if data accessed
- [ ] Document incident timeline

---

## 2. Production Database Restore

```bash
# Download latest backup (from Supabase Storage or Railway backup)
# Restore to a new database first (never restore directly to prod)
psql $STAGING_DATABASE_URL < backup-YYYYMMDD.sql

# Verify data integrity
psql $STAGING_DATABASE_URL -c "SELECT COUNT(*) FROM crm_student;"

# If good, restore to prod (during maintenance window)
psql $DATABASE_URL < backup-YYYYMMDD.sql

# Run migrations (if backup is from older version)
python manage.py migrate --run-syncdb
```

---

## 3. Application Rollback

```bash
# Via Railway UI (preferred)
# Railway → Service → Deployments → Previous deploy → Redeploy

# Via git (if Railway CI/CD fails)
git log --oneline -10
git revert <bad-commit-hash>
git push origin main
```

---

## 4. Redis Failure Recovery

If Redis goes down, WebSocket messaging will fail but the rest of the app continues.

```bash
# Check Redis status
redis-cli ping

# Restart Redis (Railway handles this automatically)
# Check Railway → Redis plugin → Restart

# Temporary fallback: switch to InMemoryChannelLayer (single-worker only)
# Set in Railway env vars:
# REDIS_URL=  (empty — will cause channels_redis to fail, but fallback needed)
```

---

## 5. Compromised User Account Response

```bash
# Via Django admin or shell
python manage.py shell

from apps.users.models import User
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

# Disable account
user = User.objects.get(email="compromised@example.com")
user.is_active = False
user.save()

# Blacklist all outstanding tokens
for token in OutstandingToken.objects.filter(user=user):
    BlacklistedToken.objects.get_or_create(token=token)

# Force password reset
user.set_password(None)  # Unusable password
user.save()
```

---

## 6. Outage Response Checklist

```
[ ] Check Railway service status
[ ] Check /api/health/ endpoint (should return 200)
[ ] Check Railway logs for errors
[ ] Check Sentry for error spikes
[ ] Check PostgreSQL connection (Railway DB plugin status)
[ ] Check Redis connection (Railway Redis plugin status)
[ ] If DB issue: check pending migrations (python manage.py showmigrations)
[ ] If migration failure: rollback migration, fix, redeploy
[ ] Notify users if outage > 15 minutes
```

---

## 7. Deployment Failure Recovery

```bash
# If new deployment fails to start:
# 1. Railway → Deployments → Rollback to previous

# If migration fails:
# Check logs for specific migration error
# Fix migration file
# Redeploy

# If environment variable missing:
# Add to Railway env vars
# Trigger manual redeploy

# Emergency: skip migration (data-safe migrations only)
python manage.py migrate --fake <app> <migration_number>
```
