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
| Login per-username rate limiting | ❌ MISSING | HIGH-002 |
| Password reset per-IP limiting | ✅ DONE | `PasswordResetRateThrottle` |
| Password reset per-email limiting | ❌ MISSING | HIGH-002 |
| Secure token generation (`secrets.token_urlsafe`) | ✅ DONE | `PasswordResetToken.mint()` |
| JWT logout endpoint (token blacklist) | ❌ MISSING | HIGH-001 |
| Session expiry configured | ❌ MISSING | HIGH-003 |
| Session HttpOnly cookie | ❌ MISSING | HIGH-003 |
| Session Secure cookie (HTTPS only) | ⚠️ PARTIAL | Only when `not DEBUG` |
| Session SameSite cookie | ❌ MISSING | HIGH-003 |
| JWT absolute maximum lifetime | ❌ MISSING | HIGH-004 |
| Email verification on registration | ❌ MISSING | Future feature |
| MFA / TOTP for admin accounts | ❌ MISSING | LOW-009 |

---

## Data Protection Controls

| Control | Status | Notes |
|---|---|---|
| Passwords hashed (Django PBKDF2) | ✅ DONE | Django default |
| CSRF protection on all HTML forms | ✅ DONE | `{% csrf_token %}` everywhere |
| XSS protection (template auto-escape) | ✅ DONE | Django template engine |
| PII fields encrypted at rest | ❌ MISSING | HIGH-005 |
| Sensitive data masked in logs | ❌ MISSING | MED-004 |
| Soft delete (no hard PII erasure) | ❌ MISSING | MED-010 |
| Database SSL connection | ✅ DONE | `ssl_require=not DEBUG` |

---

## Transport Security Controls

| Control | Status | Notes |
|---|---|---|
| HTTPS enforced (Railway auto) | ✅ DONE | Railway provisions HTTPS |
| `SECURE_SSL_REDIRECT` in production | ✅ DONE | Enabled when not DEBUG |
| HSTS configured (1 hour) | ✅ DONE | `SECURE_HSTS_SECONDS=3600` |
| HSTS subdomains included | ✅ DONE | `HSTS_INCLUDE_SUBDOMAINS=True` |
| HSTS preload | ✅ DONE | `HSTS_PRELOAD=True` |
| Secure cookies (HTTPS only) | ⚠️ PARTIAL | Tied to DEBUG flag |

---

## Input Security Controls

| Control | Status | Notes |
|---|---|---|
| SQL injection protected (ORM) | ✅ DONE | Django ORM parameterizes all queries |
| File MIME type validation | ✅ DONE | `apps/files/views.py` |
| File size limits (10 MB) | ✅ DONE | `MAX_UPLOAD_SIZE_BYTES` |
| File extension whitelist | ✅ DONE | `ALLOWED_UPLOAD_EXTENSIONS` |
| Payload size limit (`DATA_UPLOAD_MAX_MEMORY_SIZE`) | ❌ MISSING | Add to settings |
| Malware scanning on uploads | ❌ MISSING | HIGH-008 |
| Phone number validation | ❌ MISSING | LOW-004 |

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
| Secrets only in environment variables | ❌ CRITICAL | CRIT-001 — secrets in `.env` |
| SECRET_KEY enforced in production | ❌ MISSING | CRIT-004 |
| DEBUG=False enforced in production | ❌ MISSING | CRIT-005 |
| CORS origin whitelist validated | ⚠️ PARTIAL | Configured but not validated at startup |
| CSRF trusted origins validated | ⚠️ PARTIAL | Configured but not validated at startup |
| Non-root Docker user | ⚠️ UNKNOWN | Needs verification |
| Dependency pinning | ✅ DONE | `requirements.txt` has version ranges |
| `.env` excluded from git | ⚠️ UNKNOWN | Verify `.gitignore` |

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

---

## Observability & Incident Response

| Control | Status | Notes |
|---|---|---|
| Structured logging (JSON) | ❌ MISSING | MED-004 |
| Error tracking (Sentry) | ❌ MISSING | LOW-011 |
| Health check endpoint | ❌ MISSING | HIGH-006 |
| Audit log with IP address | ❌ MISSING | MED-005 |
| Database backup automation | ❌ MISSING | MED-007 |
| Secret rotation procedure documented | ❌ MISSING | docs/incident_recovery.md |
| Incident response playbook | ❌ MISSING | docs/incident_recovery.md |
