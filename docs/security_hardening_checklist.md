# Security Hardening Checklist
> Tracks the security posture of the Intelligent Education CRM.
> Updated as each control is implemented.

---

## Authentication Controls

| Control | Status | Notes |
|---|---|---|
| JWT short-lived access tokens (15 min) | ✅ DONE | Configured in settings |
| Refresh token rotation with blacklist | ✅ DONE | `ROTATE_REFRESH_TOKENS=True` |
| Login IP rate limiting (5/min) | ✅ DONE | `LoginRateThrottle` |
| Login per-username rate limiting | ✅ DONE | HIGH-002 complete |
| Password reset per-IP limiting | ✅ DONE | `PasswordResetRateThrottle` |
| Password reset per-email limiting | ✅ DONE | HIGH-002 complete |
| Secure token generation (`secrets.token_urlsafe`) | ✅ DONE | `PasswordResetToken.mint()` |
| JWT logout endpoint (token blacklist) | ✅ DONE | HIGH-001 complete |
| Session expiry configured | ✅ DONE | HIGH-003 complete |
| Session HttpOnly cookie | ✅ DONE | HIGH-003 complete |
| Session Secure cookie (HTTPS only) | ✅ DONE | `SESSION_COOKIE_SECURE=not DEBUG` |
| Session SameSite cookie | ✅ DONE | HIGH-003 complete |
| JWT absolute maximum lifetime | ✅ DONE | HIGH-004 complete |
| Email verification on registration | ❌ MISSING | Future feature |
| MFA / TOTP for admin accounts | ✅ DONE | LOW-009 complete — `django-otp` TOTP |

---

## Data Protection Controls

| Control | Status | Notes |
|---|---|---|
| Passwords hashed (Django PBKDF2) | ✅ DONE | Django default |
| CSRF protection on all HTML forms | ✅ DONE | `{% csrf_token %}` everywhere |
| XSS protection (template auto-escape) | ✅ DONE | Django template engine |
| PII fields encrypted at rest | ✅ DONE | HIGH-005 complete — passport, income, emergency contact AES-128 encrypted via Fernet |
| Sensitive data masked in logs | ✅ DONE | Passwords/tokens never logged |
| Soft delete (no hard PII erasure) | ✅ DONE | MED-010 complete |
| Database SSL connection | ✅ DONE | `ssl_require=not DEBUG` |

---

## Transport Security Controls

| Control | Status | Notes |
|---|---|---|
| HTTPS enforced (Railway auto) | ✅ DONE | Railway provisions HTTPS |
| `SECURE_SSL_REDIRECT` in production | ✅ DONE | Enabled when not DEBUG |
| HSTS configured (1 hour) | ✅ DONE | `SECURE_HSTS_SECONDS=3600` |
| HSTS subdomains included | ✅ DONE | `HSTS_INCLUDE_SUBDOMAINS=True` |
| HSTS preload | ✅ DONE | `HSTS_PRELOAD=True` — LOW-012 verified |
| Secure cookies (HTTPS only) | ✅ DONE | `SESSION_COOKIE_SECURE=not DEBUG`, `CSRF_COOKIE_SECURE=not DEBUG` |

---

## Input Security Controls

| Control | Status | Notes |
|---|---|---|
| SQL injection protected (ORM) | ✅ DONE | Django ORM parameterizes all queries |
| File MIME type validation | ✅ DONE | `apps/files/views.py` |
| File size limits (10 MB) | ✅ DONE | `MAX_UPLOAD_SIZE_BYTES` |
| File extension whitelist | ✅ DONE | `ALLOWED_UPLOAD_EXTENSIONS` |
| Payload size limit (`DATA_UPLOAD_MAX_MEMORY_SIZE`) | ✅ DONE | HIGH-004 complete — 15 MB limit |
| Malware scanning on uploads | ✅ DONE | HIGH-008 complete — 5-layer scanner (extension, magic, zip-bomb, pattern, VirusTotal) |
| Phone number validation | ✅ DONE | LOW-004 complete — E.164 regex on User.phone, Student phone fields |

---

## Security Headers

| Header | Status | Notes |
|---|---|---|
| Content-Security-Policy | ✅ DONE | `SecurityHeadersMiddleware` |
| X-Frame-Options: DENY | ✅ DONE | Django setting |
| X-Content-Type-Options: nosniff | ✅ DONE | `SECURE_CONTENT_TYPE_NOSNIFF` |
| Permissions-Policy | ✅ DONE | `SecurityHeadersMiddleware` |
| Referrer-Policy: same-origin | ✅ DONE | `SECURE_REFERRER_POLICY` |
| HSTS (Strict-Transport-Security) | ✅ DONE | Enabled in prod |
| X-XSS-Protection | ✅ DONE | `SECURE_BROWSER_XSS_FILTER` |

---

## Infrastructure Security Controls

| Control | Status | Notes |
|---|---|---|
| Secrets only in environment variables | ✅ DONE | CRIT-001 complete |
| SECRET_KEY enforced in production | ✅ DONE | CRIT-004 complete |
| DEBUG=False enforced in production | ✅ DONE | CRIT-005 complete |
| CORS origin whitelist validated | ✅ DONE | HIGH-007 complete — startup validation |
| CSRF trusted origins validated | ✅ DONE | MED-009 complete — startup validation |
| Non-root Docker user | ⚠️ UNKNOWN | Needs verification |
| Dependency pinning | ✅ DONE | `requirements.txt` has version ranges |
| `.env` excluded from git | ✅ DONE | `.git/info/exclude` confirmed |
| Docker HEALTHCHECK | ✅ DONE | LOW-005 complete — both Dockerfiles |

---

## Storage Security Controls

| Control | Status | Notes |
|---|---|---|
| Files stored on persistent storage | ✅ DONE | CRIT-003 complete — Supabase Storage |
| Upload files survive Railway redeploy | ✅ DONE | CRIT-003 complete |
| Upload retry handling | ✅ DONE | 3× retry with exponential backoff |
| Malware scan before persistence | ✅ DONE | HIGH-008 complete |
| Magic-byte disguise attack prevention | ✅ DONE | HIGH-008 complete |
| Zip-bomb protection | ✅ DONE | HIGH-008 complete |
| Dangerous content pattern detection | ✅ DONE | HIGH-008 complete |
| VirusTotal API integration (optional) | ✅ DONE | HIGH-008 — enabled via `VIRUSTOTAL_API_KEY` |

---

## API Security Controls

| Control | Status | Notes |
|---|---|---|
| All API endpoints require authentication | ✅ DONE | DRF default permission class |
| Role-based access control (RBAC) | ✅ DONE | `apps/users/permissions.py` |
| IDOR protection (student → own data only) | ⚠️ PARTIAL | Needs verification |
| WebSocket authentication | ✅ DONE | Session check in consumers |
| WebSocket authorization | ✅ DONE | `_is_authorized()` check |
| Stack trace not exposed in production | ✅ DONE | DRF exception handler |
| API schema restricted to admins in production | ✅ DONE | `urls.py` |
| Cursor pagination (prevents enumeration on large datasets) | ✅ DONE | LOW-002 complete |

---

## Observability & Incident Response

| Control | Status | Notes |
|---|---|---|
| Structured logging (JSON) | ✅ DONE | MED-004 complete |
| Error tracking (Sentry) | ✅ DONE | LOW-011 complete — auto-enabled via `SENTRY_DSN` |
| Health check endpoint | ✅ DONE | HIGH-006 complete — DB + Redis + Storage probes |
| Audit log with IP address | ✅ DONE | MED-005 complete |
| Database backup automation | ❌ MISSING | MED-007 — document + script needed |
| Secret rotation procedure documented | ✅ DONE | docs/incident_recovery.md |
| Incident response playbook | ✅ DONE | docs/incident_recovery.md |

---

## New Environment Variables Required (Phase 7)

| Variable | Required | Notes |
|---|---|---|
| `FIELD_ENCRYPTION_KEY` | **REQUIRED in prod** | Fernet key for PII encryption. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `VIRUSTOTAL_API_KEY` | Optional | Enables VirusTotal API scanning on uploads |
| `MFA_ISSUER` | Optional | Shown in authenticator apps (default: "Intelligent Education CRM") |
