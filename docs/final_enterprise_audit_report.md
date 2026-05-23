# Intelligent Education CRM — Final Enterprise Audit Report

**Prepared by:** Enterprise Audit Framework (Principal Architect · Senior Cybersecurity Auditor · DevSecOps · Django Performance Specialist · QA Lead)
**Date:** 2026-05-23
**Scope:** Full-stack CRM platform — backend, frontend, APIs, auth, infrastructure, WebSockets, Redis, Celery, Supabase, storage, CI/CD, testing, observability, operations, scalability, compliance
**Classification:** Confidential — Internal Engineering & Leadership Use Only

---

## TABLE OF CONTENTS

1. Executive Summary
2. System Inventory
3. Security Audit
4. Infrastructure Audit
5. Database Audit
6. Performance Audit
7. Observability & Operations Audit
8. WebSocket Audit
9. Celery & Async Audit
10. Storage Audit
11. Testing & QA Audit
12. Frontend Audit
13. DevOps & CI/CD Audit
14. Business Workflow Audit
15. Compliance & Governance
16. Scalability Roadmap
17. Incident Recovery Review
18. Final Scorecard
19. Final Verdict
20. Action Plan

---

## SECTION 1 — EXECUTIVE SUMMARY

### 1.1 System Overview

The Intelligent Education CRM is a Django 5 + Django Channels platform serving an international student recruitment workflow. It manages the full counselor-to-student lifecycle: lead capture, student profiling, school/course assignment, document management, follow-ups, messaging, and analytics. The system has undergone significant progressive hardening through eight documented phases, evolving from an MVP into a security-aware platform with encryption, MFA, Redis caching, Celery async tasks, Supabase cloud storage, and structured CI/CD.

### 1.2 Production Readiness Scoreboard

| Dimension | Score (0–10) | Assessment |
|---|---|---|
| **Security** | 7.4 / 10 | Strong fundamentals; specific gaps remain |
| **Infrastructure** | 6.8 / 10 | Solid Railway/Docker setup; no staging env |
| **Performance** | 6.5 / 10 | Caching in place; N+1 risks in dashboard |
| **Scalability** | 5.5 / 10 | Adequate to 500 users; redesign needed for 5K+ |
| **Observability** | 6.2 / 10 | Sentry + JSON logs + audit trail; alerting incomplete |
| **Testing** | 6.0 / 10 | 70% coverage floor; WebSocket & load tests missing |
| **Architecture** | 7.0 / 10 | Clean separation; monolith appropriate for scale |
| **Maintainability** | 7.5 / 10 | Well-structured apps; good naming; limited comments |
| **DevOps / CI/CD** | 7.0 / 10 | Solid pipeline; no staging gate, no canary |
| **Operational Maturity** | 5.5 / 10 | Health checks exist; on-call runbook absent |
| **Business Workflow Maturity** | 6.5 / 10 | Core flows complete; automation limited |
| **Overall Production Readiness** | **6.5 / 10** | Conditionally production-ready (see verdict) |

### 1.3 Biggest Strengths

1. **Multi-layer file security** — 5-layer scanner (extension block, magic bytes, zip-bomb, dangerous patterns, VirusTotal) is enterprise-grade.
2. **JWT blacklisting + refresh rotation** — prevents token replay after logout.
3. **PII field-level encryption** — Fernet AES encryption on passport numbers, income fields, emergency contacts.
4. **Structured startup validation** — production refuses to start without required env vars; no silent degradation.
5. **Soft-delete everywhere** — students, documents, files — no data loss on "delete" operations.
6. **Redis-backed WebSocket security** — per-user rate limiting, connection limits, heartbeat/ping-pong.
7. **Anomaly detection** — brute-force detection, impossible velocity, token abuse tracking.
8. **CSP middleware** — `frame-ancestors: none`, base-uri, form-action restrictions.
9. **Celery reliability** — `acks_late`, `reject_on_worker_lost`, soft/hard timeouts, retry logic.
10. **CI/CD pipeline** — bandit SAST, pip-audit CVE scanning, secret detection, migration safety checks, Docker build validation.

### 1.4 Biggest Risks

1. **No staging environment** — code ships directly from CI to production; no integration validation gate.
2. **SQLite fallback in development** — tests may pass against SQLite but fail against PostgreSQL behavior.
3. **Hardcoded dev encryption key in settings** — `FIELD_ENCRYPTION_KEY` has a fallback literal string that would silently protect nothing if the env var were accidentally unset in production.
4. **HSTS at 1 hour** — attackable via HTTPS downgrade within that window; must be promoted to 1 year.
5. **No rate limiting on WebSocket message content size** — long message strings are not capped.
6. **Student code generation race condition** — `generate_student_code()` uses `aggregate(Max(...))` without a database lock; concurrent student creation can produce duplicate codes.
7. **Backup stored in same Supabase bucket as user files** — no isolation between business data and recovery artifacts.
8. **No queue depth monitoring** — Celery queue depth has no alert; silent accumulation under load.
9. **CSV export exposes all students without PII masking** — counselors can download the entire student roster including email and phone.
10. **No load/stress testing** — no evidence of benchmark results at any user scale.

### 1.5 Deployment Readiness Verdict

> **CONDITIONALLY PRODUCTION-READY** for pilot deployments serving up to 200 concurrent users with the following immediate conditions resolved: (a) staging environment established, (b) HSTS promoted to one year, (c) student code race condition patched, (d) backup bucket isolation confirmed, (e) WS message content length capped. The platform is NOT enterprise SaaS-ready without addressing the scalability, monitoring alerting, and operational runbook gaps described in Sections 6, 7, and 16.

---

## SECTION 2 — SYSTEM INVENTORY

### 2.1 Application Inventory

| App | Purpose | Key Models |
|---|---|---|
| `apps.users` | Auth, user management, MFA | `User`, `PasswordResetToken` |
| `apps.crm` | Core CRM: students, leads, schools | `Student`, `Lead`, `School`, `Course`, `FollowUp`, `Enquiry`, `StudentActivity` |
| `apps.files` | Upload management, soft-delete | `FileObject` |
| `apps.audit` | Immutable audit trail | `ActivityLog` |
| `apps.notifications` | In-app notification system | `Notification` |
| `apps.chat` | Student-counselor real-time messaging | `ChatMessage`, `DirectMessage` |
| `apps.frontend` | Django view shim for HTML templates | (no models) |
| `apps.common` | Shared: middleware, pagination, email, health, cache service, storage, security | (no models) |

### 2.2 Service Map

```
Internet
   │
   ▼
Railway (HTTPS / WSS)
   │
   ▼
Daphne ASGI Server
   │
   ├─── HTTP ──────────────────────────────────────────────────┐
   │    Django WSGI routes                                     │
   │    ├── /api/auth/*        — JWT authentication           │
   │    ├── /api/crm/*         — Student/Lead/School CRUD     │
   │    ├── /api/files/*       — File upload/delete           │
   │    ├── /api/audit/*       — Audit log read               │
   │    ├── /api/notifications/* — Notification management    │
   │    ├── /api/health/       — Health probe (no auth)       │
   │    ├── /api/schema|docs/  — OpenAPI (admin only)         │
   │    ├── /admin/            — Django admin                 │
   │    └── /                  — HTML template pages          │
   │                                                           │
   └─── WebSocket ─────────────────────────────────────────────┘
        ├── ws/chat/<student_id>/     — Student-counselor chat
        ├── ws/dm/<other_user_id>/   — Counselor-counselor DM
        └── ws/notifications/        — Push notifications

External Dependencies:
  PostgreSQL (Railway)     — Primary database
  Redis (Railway)          — Channel layers, Celery broker, cache, anomaly detection
  Supabase Storage         — File/document CDN storage
  Celery Workers           — Async email, backup, cleanup tasks
  Celery Beat              — Scheduled periodic tasks
  Sentry                   — Error tracking (opt-in via SENTRY_DSN)
  Gmail SMTP               — Transactional email
  VirusTotal API           — File reputation (opt-in)
```

### 2.3 Request Lifecycle

```
Client → Railway TLS termination → Daphne ASGI
  → SecurityMiddleware (HTTPS redirect, HSTS)
  → WhiteNoiseMiddleware (static files)
  → RequestCorrelationMiddleware (X-Request-ID assign)
  → CorsMiddleware
  → SessionMiddleware
  → CommonMiddleware
  → CsrfViewMiddleware
  → AuthenticationMiddleware (JWT decode)
  → MessageMiddleware
  → XFrameOptionsMiddleware
  → SecurityHeadersMiddleware (CSP, CORP, COOP)
  → SecurityEventLoggingMiddleware (401/403/429 logging)
  → View (DRF permission check → throttle check → serializer → DB → response)
```

### 2.4 Async Task Lifecycle

```
Signal / View triggers → Celery task.delay()
  → Redis broker (queue: "default")
  → Celery worker picks up task
  → Task executes (email, backup, cleanup, audit log)
  → Result stored in Redis backend
  → Beat scheduler fires periodic tasks (cron)
```

### 2.5 Upload Lifecycle

```
Client POST /api/files/upload/ (multipart)
  → Extension validation (_ALLOWED_EXTS)
  → Size validation (≤10 MB)
  → MIME type resolution (mimetypes.guess_type > Content-Type header)
  → 5-layer malware scan (scan_file())
  → Supabase Storage upload (3-attempt retry)
    OR local filesystem (dev fallback)
  → FileObject.objects.create() (DB record)
  → 201 response with file metadata + public_url
```

### 2.6 WebSocket Lifecycle

```
Client → wss://<host>/ws/chat/<student_id>/
  → AllowedHostsOriginValidator (origin check vs ALLOWED_HOSTS)
  → AuthMiddlewareStack (JWT or session auth)
  → ChatConsumer.connect()
      → is_authenticated check (close 4001 if not)
      → _is_authorized() (student/counselor/admin check)
      → _check_connection_limit() (Redis counter; max 5 per user)
      → channel_layer.group_add()
      → accept()
  → ChatConsumer.receive()
      → _check_message_rate() (60 msg/min per user)
      → Parse JSON, handle pong
      → _save_message() → DB
      → group_send() → all members of room
      → _create_chat_notifications() → notification WS push
  → ChatConsumer.disconnect()
      → group_discard()
      → _decrement_connection_count()
```

---

## SECTION 3 — SECURITY AUDIT

### 3.1 Authentication

#### JWT Implementation

| Check | Status | Notes |
|---|---|---|
| Short access token lifetime | ✅ PASS | 15 minutes (configurable) |
| Refresh token rotation | ✅ PASS | `ROTATE_REFRESH_TOKENS = True` |
| Blacklist on rotation | ✅ PASS | `BLACKLIST_AFTER_ROTATION = True` |
| Last login tracking | ✅ PASS | `UPDATE_LAST_LOGIN = True` |
| Token type confusion prevention | ✅ PASS | `AUTH_TOKEN_CLASSES` restricts to AccessToken |
| Refresh token 7-day lifetime | ✅ PASS | Default 7 days, configurable |
| Blacklist table purge | ✅ PASS | Celery Beat task at 03:00 daily |

**Finding AUTH-001 — MEDIUM:** The `RefreshView` is `AllowAny` at the class level. If a stolen (but not yet expired) refresh token is presented after logout, the blacklist check occurs within simplejwt's rotation logic. This works correctly. However, there is no IP-binding on token issuance; a token stolen before logout can be rotated from any IP indefinitely until it expires naturally.

**Finding AUTH-002 — LOW:** No `jti` claim validation for concurrent refresh requests. Under race conditions (multiple simultaneous refresh calls with the same token), simplejwt's blacklist prevents double-use correctly, but the error messaging is opaque to clients.

#### Password Reset Flow

| Check | Status | Notes |
|---|---|---|
| Account enumeration prevention | ✅ PASS | Always returns same response |
| Per-IP rate limiting | ✅ PASS | `PasswordResetRateThrottle` 3/min |
| Per-email rate limiting | ✅ PASS | Max 2 tokens per 15-minute window |
| Token expiry (30 min) | ✅ PASS | `PasswordResetToken.mint(ttl_minutes=30)` |
| Single-use enforcement | ✅ PASS | `used_at` checked via `is_valid()` |
| Secure token generation | ✅ PASS | `secrets.token_urlsafe(32)` = 256 bits |

**Finding AUTH-003 — MEDIUM:** The password reset token is delivered via reset link in plaintext email. The `PasswordResetToken` is stored in the database unhashed. If the database is compromised during the token's 30-minute window, all active reset tokens are exploitable. Industry standard is to store a hash (e.g., SHA-256) of the token in the database and compare the hash on validation.

**Finding AUTH-004 — LOW:** `PasswordResetToken` records are never hard-deleted after use — only `used_at` is set. Over time this table will accumulate indefinitely. A Celery Beat task should prune expired tokens (separate from JWT blacklist purge).

#### Login Throttling & Brute-Force Protection

| Check | Status | Notes |
|---|---|---|
| Per-IP login rate limit | ✅ PASS | `LoginRateThrottle` (5/min via DRF) |
| Failed login anomaly detection | ✅ PASS | `record_failed_login()` — 5 failures in 5 min |
| Impossible velocity detection | ✅ PASS | Different /16 subnet within 5 min |
| Token abuse detection | ✅ PASS | 3 invalid tokens in 2 min |
| Account lockout | ❌ MISSING | No account lockout after N failures |

**Finding AUTH-005 — HIGH:** There is no account lockout mechanism. The 5/min rate limit applies per IP, but an attacker using a rotating IP pool (e.g., residential proxy network) or distributing across many IPs can attempt unlimited password combinations. The anomaly detection will log events, but no automated blocking or lockout occurs. **Recommendation:** Implement CAPTCHA after 3 failures, or account soft-lock (5-minute cooldown) after 10 failures per email, resettable by admin.

**Finding AUTH-006 — LOW:** The impossible-velocity check uses a /16 subnet comparison. A VPN user changing servers within the same /16 (common in corporate VPNs) will not be flagged, which is correct, but it also means attackers with IPs in the same /16 are never flagged regardless of behavioral patterns.

### 3.2 Authorization (RBAC)

| Role | Can Access Students | Can Access Leads | Can Manage Schools | Can View Audit Log | Can Admin |
|---|---|---|---|---|---|
| Admin | ✅ Full | ✅ Full | ✅ Full | ✅ Yes | ✅ Yes |
| Counselor | ✅ Full | ✅ Full | List/retrieve only | ❌ No (403) | ❌ No |
| Editor | ❌ (see below) | ❌ No | ❌ No | ❌ No | ❌ No |
| Student | Own profile only | ❌ No | List active only | ❌ No | ❌ No |

**Finding AUTHZ-001 — HIGH:** The `Editor` role is defined (`Role.EDITOR`) and has a permission class (`IsEditorOrAdmin`, `IsCounselorEditorOrAdmin`) but these permission classes are **not applied to any viewset in `views_api.py`**. The `StudentViewSet.get_permissions()` only uses `IsCounselorOrAdmin` — editors cannot access students at all. If editors are supposed to manage documents and applications, this is a broken business workflow. If editors are not supposed to, the role documentation is misleading.

**Finding AUTHZ-002 — MEDIUM:** The `StudentViewSet` does not enforce counselor-level scoping on student listing. A counselor can retrieve any student, not just students assigned to them (`counselor=request.user`). This is a data isolation gap — a counselor at one organization can access another counselor's students. This may be intentional for the single-org use case, but must be explicitly documented and is a GDPR concern in multi-org deployments.

**Finding AUTHZ-003 — MEDIUM:** In `StudentPreferenceViewSet.get_queryset()`, a student user gets filtered to their own preferences correctly. However, a non-student user gets `StudentPreference.objects.all()` — unfiltered. If a counselor accidentally targets another counselor's student's preferences (by ID), no object-level permission check prevents the read.

**Finding AUTHZ-004 — LOW:** The `DashboardViewSet` returns aggregate counts for all students/leads regardless of the requesting counselor's assignments. This exposes aggregate business intelligence to any counselor. Not an access violation, but a data minimization concern.

**Finding AUTHZ-005 — LOW:** `FileDeleteView` checks `is_owner or is_privileged (counselor/admin)`. Editors are not privileged for deletion. However, editors cannot upload via standard flow either (no explicit editor permission check in `FileUploadView` — any authenticated user can upload). This asymmetry should be documented or fixed.

### 3.3 Input Security

| Check | Status | Notes |
|---|---|---|
| Extension allowlist | ✅ PASS | Hardcoded set in settings |
| Size limit (10 MB global) | ✅ PASS | `DATA_UPLOAD_MAX_MEMORY_SIZE` + per-view check |
| MIME type validation | ⚠️ PARTIAL | Uses `mimetypes.guess_type` (filename-based), not libmagic |
| Magic byte validation | ✅ PASS | Layer 2 of file scanner |
| Zip bomb protection | ✅ PASS | 50x ratio + 200 MB uncompressed cap |
| Dangerous pattern scan | ✅ PASS | PE headers, ELF, shebang, PDF JS actions |
| VirusTotal integration | ✅ OPTIONAL | Configured via `VIRUSTOTAL_API_KEY` |
| SQL injection | ✅ PASS | Django ORM used throughout; no raw SQL |
| XSS | ✅ PASS | DRF JSON responses; Django template auto-escaping |
| CSRF | ✅ PASS | `CsrfViewMiddleware` active; JWT APIs are CSRF-exempt by design |

**Finding INPUT-001 — MEDIUM:** MIME type detection in `_validate_upload()` uses `mimetypes.guess_type(file.name)` — this is filename-based, not content-based. An attacker can upload a malicious binary named `document.pdf` and the `mimetypes` lookup will return `application/pdf` regardless of file content. The magic-byte check in `scan_file()` compensates for this, but the MIME validation in the view layer gives false assurance. These two systems should be unified: validate MIME from magic bytes only.

**Finding INPUT-002 — LOW:** CSV and TXT files have no magic-byte check (intentionally, as noted in the scanner). However, a CSV file containing formulas (`=cmd|'/c calc.exe'!A0`) can be a CSV injection attack if the exported data is opened in Excel. The upload is permitted; the risk materializes on download/export.

**Finding INPUT-003 — LOW:** Message content in WebSocket `receive()` is saved to the database with only `.strip()` — no length cap on the message `content` field. The `ChatMessage` model's `content` column is a `TextField` (unlimited). A single WebSocket message of 10 MB will pass rate limiting (which counts message count, not byte volume) and be written to the database.

**Finding INPUT-004 — LOW:** The `student_code` generator uses `generate_student_code()` which reads `MAX("student_code")` without a `SELECT FOR UPDATE` or `UNIQUE` constraint race protection beyond the model-level `unique=True`. Under concurrent creates (race condition within a few milliseconds), two processes could read the same `MAX` and attempt to create `STU-0002` simultaneously. The `unique=True` constraint will cause one to fail with an `IntegrityError` at the DB level, but the application does not retry — the user gets a 500 error.

### 3.4 Transport Security

| Check | Status | Notes |
|---|---|---|
| HTTPS redirect (production) | ✅ PASS | `SECURE_SSL_REDIRECT=True` when `DJANGO_SECURE_SSL_REDIRECT=1` |
| HSTS enabled | ⚠️ WEAK | `SECURE_HSTS_SECONDS = 3600` (1 hour) — too short |
| HSTS subdomains | ✅ PASS | `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` |
| HSTS preload | ✅ PASS | `SECURE_HSTS_PRELOAD = True` |
| Session cookie secure | ✅ PASS | `SESSION_COOKIE_SECURE = not DEBUG` |
| CSRF cookie secure | ✅ PASS | `CSRF_COOKIE_SECURE = not DEBUG` |
| X-Frame-Options DENY | ✅ PASS | `X_FRAME_OPTIONS = "DENY"` |
| X-Content-Type-Options | ✅ PASS | `SECURE_CONTENT_TYPE_NOSNIFF = True` |
| Referrer-Policy | ✅ PASS | `same-origin` |
| COOP | ✅ PASS | `same-origin` |
| CORP | ✅ PASS | `same-origin` |
| COEP | ⚠️ OMITTED | Intentionally disabled; documented in code |

**Finding TRANSPORT-001 — HIGH:** `SECURE_HSTS_SECONDS = 3600` (1 hour) is dangerously low. HSTS preload requires a minimum of 31,536,000 seconds (1 year). The current value means that if a user clears their browser cache or uses a new browser, they are not protected from HTTPS downgrade attacks for up to 59 minutes. This should be promoted to `31536000` once the deployment is stable.

**Finding TRANSPORT-002 — MEDIUM:** The CSP includes `'unsafe-inline'` for both `script-src` and `style-src`. This significantly weakens XSS protection — any injected `<script>` or `<style>` tag in the HTML output will execute. The reason is that Tailwind CDN and Google Fonts are used without nonce-based CSP. **Recommendation:** Move to a bundled Tailwind CSS file (no CDN needed in production), remove `'unsafe-inline'` from `script-src`, and implement nonce-based CSP.

**Finding TRANSPORT-003 — LOW:** CORS allowed origins are injected from `DJANGO_CORS_ALLOWED_ORIGINS` (comma-delimited). If this env var is misconfigured with a trailing comma, an empty-string origin could be in the list. The current parsing filters empty strings, so this is handled.

**Finding TRANSPORT-004 — LOW:** The WebSocket connection URL routing in `asgi.py` uses `AllowedHostsOriginValidator`. This validates the `Origin` header against `ALLOWED_HOSTS` but does not enforce WSS in production (vs WS). WebSocket protocol security (WSS) depends entirely on the Railway TLS terminator. This is acceptable in practice but should be documented.

### 3.5 Secrets Management

| Check | Status | Notes |
|---|---|---|
| Production startup validation | ✅ PASS | Missing vars raise `RuntimeError` at boot |
| Secret key fallback | ✅ PASS | Falls back only in dev, raises in production |
| Debug mode validation | ✅ PASS | Raises if `DEBUG=1` in production |
| Encryption key fallback | ⚠️ WARNING | Falls back to a literal string instead of raising |
| Email password in logs | ✅ PASS | Not logged anywhere; password logged only if DEBUG |
| Sentry PII scrubbing | ✅ PASS | `_sentry_scrub_pii()` removes sensitive fields |
| `.env` excluded from VCS | Assumed OK | `.env` in `.gitignore` (not verified) |

**Finding SECRETS-001 — HIGH:** `FIELD_ENCRYPTION_KEY` degrades silently with a warning log rather than a startup crash in production. The fallback key `NpY4Ttx1ztyDl--COHI7o5b2X3aj3SFX_40AGe2KjlU=` is now embedded in the repository, meaning if the env var is ever accidentally unset, PII fields will silently be encrypted with a publicly-known key. **Recommendation:** Change the behavior to `raise RuntimeError` in production when `FIELD_ENCRYPTION_KEY` is not set, matching the pattern used for `DJANGO_SECRET_KEY`.

**Finding SECRETS-002 — MEDIUM:** The `FIELD_ENCRYPTION_KEY` fallback value appears in `settings.py` in version control. Anyone with read access to the repository can decrypt PII fields from a database backup that used the fallback key. This must be rotated immediately if any production data was ever written using the fallback key.

**Finding SECRETS-003 — LOW:** `supabase-config.js` exists at the project root and is served dynamically from Django. The Supabase anon key is exposed to the client-side browser via this endpoint. This is by design (anon key is public), but the `SUPABASE_SERVICE_ROLE_KEY` must never appear in this file — verify this is enforced.

**Finding SECRETS-004 — LOW:** The CI workflow embeds `FIELD_ENCRYPTION_KEY: NpY4Ttx1ztyDl--COHI7o5b2X3aj3SFX_40AGe2KjlU=` as a plain-text GitHub Actions env var. This is the same key as the fallback. GitHub Actions environment variables are visible to repository contributors with write access. This should be stored as a GitHub Actions encrypted secret.

### 3.6 PII Protection

| Check | Status | Notes |
|---|---|---|
| Passport number encrypted | ✅ PASS | `EncryptedCharField` |
| Parent income encrypted | ✅ PASS | `EncryptedCharField` (father + mother) |
| Emergency contact encrypted | ✅ PASS | `EncryptedCharField` + `EncryptedEmailField` |
| PII excluded from Sentry events | ✅ PASS | `before_send` hook scrubs known PII keys |
| PII excluded from audit logs | ⚠️ PARTIAL | `metadata` field in `ActivityLog` can contain arbitrary JSON; unclear if signals sanitize before writing |
| Export masking | ❌ MISSING | CSV export includes email and phone in plaintext |
| Student list API response | ⚠️ PARTIAL | `StudentSerializer` returns full PII to any authenticated counselor |

**Finding PII-001 — MEDIUM:** The CSV student export (`/api/crm/students/export/`) streams email and phone numbers for all students without masking. Any counselor or admin can download the entire student roster. This is a GDPR data minimization violation for EU-accessible systems.

**Finding PII-002 — LOW:** The `ActivityLog.metadata` JSONField has no schema validation. If a signal or view accidentally writes a serialized student object (containing `passport_number`, which is an encrypted blob, but also `email`, `phone`, etc.) into metadata, those values are stored in plaintext in the audit log. The audit log is visible to admins.

**Finding PII-003 — LOW:** `destination_countries` is stored as a comma-separated `TextField` rather than a structured field. This makes GDPR-compliant data export or deletion more complex than necessary.

### 3.7 MFA Implementation

| Check | Status | Notes |
|---|---|---|
| TOTP standard (RFC 6238) | ✅ PASS | `django-otp` + `django_otp.plugins.otp_totp` |
| Admin-only requirement | ✅ PASS | `MFARequiredForAdmin` permission |
| Unenrolled admin pass-through | ✅ PASS | Non-enrolled admins not blocked |
| QR code enrollment endpoint | ✅ PASS | `mfa_views.py` exists |
| MFA for counselors | ❌ OPTIONAL | Counselors have no MFA requirement |

**Finding MFA-001 — MEDIUM:** MFA is only enforced for admin users via `MFARequiredForAdmin`. Counselors — who access all student PII — have no MFA requirement. In an educational context where student records are sensitive, counselor accounts should be MFA-protected, especially since they represent a high-value phishing target.

**Finding MFA-002 — LOW:** The `MFARequiredForAdmin` check queries `user.totpdevice_set.filter(confirmed=True).first()` on every request for enrolled admins. This is a database query on every authorized API call. This should be cached (e.g., per-session flag or short-lived Redis cache keyed on `user.pk`).

---

## SECTION 4 — INFRASTRUCTURE AUDIT

### 4.1 Railway Deployment

The system deploys to Railway via Docker. The `Dockerfile` is validated in CI. Railway injects environment variables, PostgreSQL, and Redis as service plugins.

**Finding INFRA-001 — CRITICAL:** There is **no staging environment**. Code goes directly from CI (GitHub Actions) to production. A failed migration, a breaking serializer change, or a Celery task regression has no pre-production catch point. This is the single highest operational risk.

**Finding INFRA-002 — HIGH:** The `SECURE_HSTS_SECONDS` at 3600 means the HSTS header is not preload-eligible and leaves a 1-hour window for downgrade attacks (see TRANSPORT-001).

**Finding INFRA-003 — MEDIUM:** The application has a single Daphne ASGI process handling both HTTP and WebSocket connections. Under high WebSocket load, HTTP requests compete with open persistent WS connections for process resources. A dedicated Daphne configuration should separate HTTP and WS workers.

**Finding INFRA-004 — MEDIUM:** `CELERY_WORKER_CONCURRENCY = 2` is the default. For email-heavy workflows (student assignments, welcome emails, password resets), 2 workers may saturate during bulk operations. Worker concurrency should scale with Railway's resource plan.

**Finding INFRA-005 — MEDIUM:** `MEDIA_ROOT` and `MEDIA_URL` are configured for local filesystem in development, but in production all files go to Supabase. If `SUPABASE_URL` is misconfigured in production, the fallback is local filesystem — on Railway this is ephemeral (wiped on redeploy). Files would be permanently lost. The startup validation should also assert `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in production.

**Finding INFRA-006 — LOW:** Redis connection parameters use `socket_connect_timeout: 3` and `socket_timeout: 3`. Under a Redis blip, HTTP requests will block for up to 3 seconds before failing. For a synchronous Django view that reads from cache, this is 3 seconds added to user-visible latency.

**Finding INFRA-007 — LOW:** The `conn_max_age=600` PostgreSQL connection pooling is appropriate for a monolith but will not work correctly behind multiple Daphne workers without a connection pooler (PgBouncer). Each worker maintains up to 600-second connections independently.

### 4.2 Docker Configuration

The `Dockerfile` is validated in CI (`docker` job). The build target is `production`. The HEALTHCHECK directive was added in Phase 7.

**Finding DOCKER-001 — MEDIUM:** The Dockerfile healthcheck command was not read directly; unable to verify its implementation. A health check that pings `localhost` without testing the actual application port may pass even if the application is deadlocked.

**Finding DOCKER-002 — LOW:** No `USER` directive to drop root privileges confirmed (not read). Running Django as root inside a container is a common misconfiguration that increases blast radius if the container is compromised.

### 4.3 Single Points of Failure

| Component | SPOF Risk | Mitigation |
|---|---|---|
| Railway Web Worker | Medium | Railway auto-restarts on crash |
| Redis | High | No Redis Sentinel; single Redis instance |
| PostgreSQL | Medium | Railway manages HA for PostgreSQL plugin |
| Supabase Storage | Low | Supabase SLA; retry logic in storage service |
| Celery Workers | Medium | Railway auto-restart; `acks_late` prevents data loss |
| Celery Beat | High | Single Beat instance; no HA Beat scheduler |

**Finding INFRA-008 — HIGH:** Celery Beat runs as a single instance. If it crashes, no scheduled tasks run until it restarts. Nightly backups, token purges, and audit log archiving silently stop. There is no monitoring alert for Beat health.

---

## SECTION 5 — DATABASE AUDIT

### 5.1 Schema Design

The schema is well-normalized for the use case. Models follow Django conventions with proper ForeignKey relationships, `auto_now`/`auto_now_add` timestamps, and `db_index=True` on frequently queried fields.

**Strengths:**
- Composite indexes on `(status, created_at)` — correct for lead/followup queries
- `(assigned_to, status)` index — correct for counselor dashboard filters
- `(actor, created_at)` index on `ActivityLog` — correct for audit searches
- `(student, school, category)` index on `StudentSchoolDocument`
- Soft-delete pattern consistent across `Student`, `StudentSchoolDocument`, `StudentProfileDocument`, `FileObject`

### 5.2 Index Analysis

| Table | Existing Indexes | Missing Indexes |
|---|---|---|
| `Student` | `(is_active, student_code)`, `(counselor, is_active)`, `deleted_at` | `(email)` — used in search, `(user_id)` — FK lookup |
| `Lead` | `(status, created_at)`, `(assigned_to, status)`, `phone`, `email` | None significant |
| `FollowUp` | `(status, scheduled_at)`, `(assigned_to, status)` | None significant |
| `ActivityLog` | `(action, created_at)`, `(entity, entity_id)`, `(actor, created_at)` | None significant |
| `Notification` | Not read — assumed indexed on `(user_id, read_at)` | Verify |
| `PasswordResetToken` | `(user, expires_at)`, `token` | None |

**Finding DB-001 — MEDIUM:** `Student.email` is not indexed but is used as a search field (`search_fields = ("student_code", "full_name", "phone", "email")`). DRF search generates `ILIKE '%<term>%'` queries — these cannot use a B-tree index, but for exact lookups by email in other parts of the system, an index would be beneficial. Consider a `GinIndex` with `pg_trgm` extension for full text search.

**Finding DB-002 — MEDIUM:** `Student.user` is a `OneToOneField` with `on_delete=SET_NULL`. The reverse lookup `Student.objects.filter(user=request.user)` appears in multiple views without an explicit index. Django adds a unique index for `OneToOneField` automatically, so this is not a problem — but it should be verified in `EXPLAIN` output.

**Finding DB-003 — HIGH:** The `generate_student_code()` method uses `Student.objects.aggregate(Max("student_code"))`. This is:
1. **Race-condition-prone** — two concurrent creates read the same MAX and both try to insert `STU-0002`
2. **Slow at scale** — `MAX()` on a text column is not index-optimal (requires full scan or sorting)
3. **Fragile** — assumes `student_code` starts with "STU-" and is numeric after that

**Recommendation:** Replace with a `PostgreSQL SEQUENCE` or Django's `BigAutoField`-based auto-increment, exposed as `STU-{pk:04d}` as a computed property.

**Finding DB-004 — MEDIUM:** The `Student` model has 60+ fields — this is a very wide table. PostgreSQL stores variable-length fields on TOAST pages, so this is less of a concern than in other databases, but it means every `SELECT *` pulls a large amount of data per row. The `StudentSerializer` should explicitly list only needed fields per endpoint context.

**Finding DB-005 — LOW:** `FollowUp.clean()` uses `full_clean()` from `save()`. This means every `FollowUp.save()` triggers a `clean()` call, adding a validation overhead. This is intentional for data integrity but should be documented.

### 5.3 Migration Safety

19 migration files exist for `crm`, all following Django conventions. The CI pipeline validates:
- No pending migrations (`makemigrations --check`)
- Consistent migration state (`migrate --check`)

**Finding DB-006 — MEDIUM:** There is no zero-downtime migration strategy documented. Django migrations that add NOT NULL columns without defaults, rename columns, or drop columns are locking operations on PostgreSQL for large tables. The migration `0019_encrypt_pii_fields.py` (field-level encryption) likely involved a data migration — if this ran on a live database with many students, it could have caused extended table locks.

**Finding DB-007 — LOW:** No database backup is verified before migration runs. The CI pipeline runs `migrate` but there is no pre-migration backup assertion. A failed migration on production with no recent backup is a data-loss risk.

### 5.4 N+1 Query Analysis

| View | Concern | Status |
|---|---|---|
| `StudentViewSet.get_queryset()` | `select_related("course", "user", "counselor", "poc")` | ✅ OK |
| `LeadViewSet` | `select_related("course_interested", "assigned_to", "created_by")` | ✅ OK |
| `DashboardViewSet.summary()` | Multiple separate `Count()` queries | ⚠️ MODERATE |
| `ChatConsumer._is_authorized()` | DB query on every WS connect | ⚠️ ACCEPTABLE |
| `StudentPreferenceViewSet.perform_create()` | `StudentActivity.objects.create()` inline | ✅ OK |
| `signals.py student_pre_save` | `Student.objects.get(pk=instance.pk)` on every `Student.save()` | ⚠️ EXTRA QUERY |

**Finding DB-008 — MEDIUM:** `DashboardViewSet.summary()` makes at least 8 separate database queries even with caching:
- `lead_by_status` — full scan with GROUP BY
- `enquiry_by_status` — full scan with GROUP BY
- `followups_next_7` — date range count
- `Lead.objects.filter(created_at__gte=last_30).count()`
- Plus 4 cached calls that may be cache misses

These should be batched into a single SQL query using `WITH` CTEs or consolidated into the cache service.

**Finding DB-009 — LOW:** `signals.student_pre_save` issues `Student.objects.get(pk=instance.pk)` on every save to capture old field values. This is a read query before every update. For bulk updates (e.g., mass counselor reassignment), this generates N+1 selects. Use `update_fields` with a pre-load pattern or Django's `F()` expressions.

### 5.5 Data Retention

| Check | Status | Notes |
|---|---|---|
| Soft-delete for students | ✅ PASS | `deleted_at` + `is_active=False` |
| Soft-delete for documents | ✅ PASS | `deleted_at` on `StudentSchoolDocument`, `StudentProfileDocument`, `FileObject` |
| Audit log archiving | ✅ PASS | Celery Beat task at midnight |
| Backup retention (30 days) | ✅ PASS | `prune_old_backups` weekly task |
| Hard-delete policy documented | ❌ MISSING | No documented procedure for permanent deletion (GDPR right to erasure) |

**Finding DB-010 — HIGH:** There is no documented or implemented procedure for GDPR right-to-erasure (Article 17). When a student requests deletion of their data, soft-delete marks the record as deleted but retains all PII fields in the database. The audit log retains references and metadata. Supabase Storage retains the physical files. A GDPR erasure path must be designed and implemented.

---

## SECTION 6 — PERFORMANCE AUDIT

### 6.1 API Response Time Estimates

Based on code analysis (no live benchmark data available):

| Endpoint | Expected p50 | Risk Factor |
|---|---|---|
| `GET /api/health/` | <20ms | DB + Redis probes |
| `POST /api/auth/login/` | 50-200ms | `authenticate()` includes password hashing |
| `GET /api/crm/students/` | 20-100ms (cached) / 100-500ms (cold) | Depends on cache state |
| `GET /api/crm/dashboard/summary/` | 30-200ms | 8+ DB queries if cache cold |
| `GET /api/crm/students/export/` | 1-30s | Depends on student count; streaming |
| `POST /api/files/upload/` | 500ms-5s | Includes file scan + Supabase upload |
| `GET /api/audit/activity-logs/` | 50-300ms | No caching; depends on log volume |

### 6.2 Performance Findings

**Finding PERF-001 — HIGH:** The file upload endpoint reads the entire file into memory (`file_bytes = file.read()`) before scanning and uploading. For a 10 MB file, this holds 10 MB in the ASGI worker's memory for the duration of the scan + Supabase upload (potentially 5-10 seconds). Under concurrent uploads, memory pressure will degrade all requests on the worker. **Recommendation:** Stream files to a temporary file, scan from the file, then stream to Supabase.

**Finding PERF-002 — MEDIUM:** The malware scanner scans the first 4 MB of content for dangerous patterns (`sample = file_bytes[:4 * 1024 * 1024]`). For a 10 MB file, 4 MB is held in memory for pattern matching plus the full 10 MB for Supabase upload. Total: 14 MB per concurrent upload.

**Finding PERF-003 — MEDIUM:** The VirusTotal check in the file scanner uses `urllib.request.urlopen()` synchronously within a Django request handler. If VirusTotal is slow (timeout=5s), the upload endpoint blocks for 5 seconds, stalling the ASGI worker thread. This should be done asynchronously (as a Celery task post-upload) or use a non-blocking HTTP client.

**Finding PERF-004 — MEDIUM:** `get_active_schools()` in the cache service caches a **list of Django ORM objects** (not serialized data). Django ORM objects are not pickle-safe in all configurations and carry references to the database connection. Serializing ORM objects to Redis is fragile and may fail across deploys if model internals change. Cache serialized data (dicts or plain Python structures) instead.

**Finding PERF-005 — LOW:** The dashboard summary makes `Course.objects.count()` and `School.objects.count()` inline, not through the cache service. These are un-cached DB calls on every dashboard load beyond the already-cached values.

**Finding PERF-006 — LOW:** `StudentViewSet.get_queryset()` always selects `select_related("course", "user", "counselor", "poc")`. For list views paginated at 20 students, this generates 1 query with 4 JOINs — efficient. However, for the export view, `select_related` is used again on `.values()` which is redundant (`.values()` doesn't instantiate objects and doesn't benefit from `select_related`). This just adds noise.

### 6.3 Cache Efficiency

| Cache Key | TTL | Invalidation Strategy | Assessment |
|---|---|---|---|
| `crm:v2:dashboard:student_counts` | 2 min | Signal on student save/delete | ✅ Good |
| `crm:v2:dashboard:lead_counts` | 2 min | Signal on lead save/delete | ✅ Good |
| `crm:v2:dashboard:course_count` | 2 min | Signal on course save | ✅ Good |
| `crm:v2:schools:active_list` | 5 min | Signal on school save/delete | ⚠️ Stores ORM objects |
| `crm:v2:dashboard:followups_due` | 60 s | No explicit invalidation | ⚠️ Stale for up to 60s |
| `crm:v2:notif:unread:<user_id>` | 30 s | Explicit delete on read/create | ✅ Good |
| `vt_safe_<sha256>` | 24 h | Not invalidated | ✅ Appropriate |

**Finding PERF-007 — MEDIUM:** `get_followups_due_today()` is not explicitly invalidated when a follow-up is marked done or created. It only expires after 60 seconds. If a counselor marks a follow-up done, the dashboard will show the stale count for up to 60 seconds. A signal on `FollowUp.save()` should invalidate `_KEY_FOLLOWUP_DUE`.

---

## SECTION 7 — OBSERVABILITY & OPERATIONS AUDIT

### 7.1 Logging

| Aspect | Status | Notes |
|---|---|---|
| Structured JSON in production | ✅ PASS | `python-json-logger`, JSON formatter when `IS_PRODUCTION` |
| Human-readable in dev | ✅ PASS | Verbose formatter in dev |
| Root logger level | ✅ PASS | `WARNING` in production, `DEBUG` in dev |
| App logger (`apps.*`) | ✅ PASS | `INFO` in production |
| Security event logger | ✅ PASS | `SecurityEventLoggingMiddleware` on 401/403/429 |
| Correlation ID in logs | ✅ PASS | `X-Request-ID` set in thread-local; available in logs |
| PII in logs | ⚠️ PARTIAL | No centralized sanitization; depends on each log call |

**Finding OBS-001 — MEDIUM:** The `X-Request-ID` is stored in thread-local storage (`_request_id_local.request_id`), but it is NOT automatically injected into log records. Developers must explicitly add `extra={"request_id": get_request_id()}` to every log call. In practice, most log statements in the codebase don't include the request ID in the `extra` dict. Log correlation across a distributed trace is therefore manual and inconsistent.

**Finding OBS-002 — MEDIUM:** There is no structured trace correlation between Celery tasks and the HTTP request that triggered them. When a `send_welcome_email_task.delay()` is called, the request ID is not propagated to the Celery worker. Debugging asynchronous task failures cannot be correlated to originating requests.

**Finding OBS-003 — LOW:** The Django `mail_admins` handler is configured at `ERROR` level in production, but no `ADMINS` setting is defined in `settings.py`. Django admin email notifications are silently disabled.

### 7.2 Sentry Integration

| Aspect | Status | Notes |
|---|---|---|
| DjangoIntegration | ✅ PASS | Enabled when SENTRY_DSN set |
| CeleryIntegration | ✅ PASS | Celery task errors tracked |
| RedisIntegration | ✅ PASS | Redis errors tracked |
| LoggingIntegration | ✅ PASS | ERROR+ emits to Sentry |
| PII scrubbing | ✅ PASS | `before_send` hook |
| Release tracking | ✅ PASS | `RAILWAY_DEPLOYMENT_ID` or `GIT_SHA` |
| Performance tracing | ✅ PASS | `traces_sample_rate = 0.1` |
| Profiles | ⚠️ DISABLED | `profiles_sample_rate = 0.0` |

**Finding OBS-004 — LOW:** Sentry is entirely optional (only enabled if `SENTRY_DSN` is set). If this env var is not configured in production (which is a realistic scenario for a new deployment), there is zero error visibility beyond console logs. This should be a production startup warning.

### 7.3 Monitoring & Alerting

| Alert Type | Status | Notes |
|---|---|---|
| Application error rate | ⚠️ PARTIAL | Sentry if configured |
| Database query time | ❌ MISSING | No query duration alerting |
| Redis memory usage | ❌ MISSING | No Redis memory alert |
| Celery queue depth | ❌ MISSING | No queue depth monitoring |
| WebSocket connection count | ✅ PARTIAL | Countable via Redis keys; no alert |
| Backup job success | ❌ MISSING | No alert if nightly backup fails |
| Worker health | ❌ MISSING | No Celery worker heartbeat alert |

**Finding OBS-005 — HIGH:** There is no alerting for Celery task failures, queue depth, or Beat health. If the nightly backup fails, nobody is notified. If a Celery worker crashes and tasks accumulate, nobody is notified until a user reports a missing email or delayed notification.

**Finding OBS-006 — HIGH:** There is no on-call runbook, incident response playbook, or escalation path documented. When a production incident occurs (database unavailable, Redis down, Supabase unreachable), engineers must improvise the recovery procedure.

### 7.4 Audit Logging

The `ActivityLog` model is well-designed with:
- IP address
- User agent
- Field-level change tracking (`changes` JSONField)
- Actor/entity/action triple

**Finding OBS-007 — MEDIUM:** The audit log is written synchronously (via `log_activity()` in signals). For high-frequency operations (bulk student imports, rapid lead updates), this adds a DB write per signal fire. These should be async Celery tasks.

**Finding OBS-008 — LOW:** The audit log `action` field is a free-text `CharField(max_length=120)`. There is no enum/schema validation. Different parts of the codebase may use different strings for the same action (`"student.created"` vs `"student_created"`). A lookup table or `TextChoices` would prevent inconsistency.

---

## SECTION 8 — WEBSOCKET AUDIT

### 8.1 Authentication

| Check | Status | Notes |
|---|---|---|
| `AllowedHostsOriginValidator` | ✅ PASS | Origin checked against `ALLOWED_HOSTS` |
| `AuthMiddlewareStack` | ✅ PASS | JWT or session token required |
| Explicit auth check in `connect()` | ✅ PASS | `user.is_authenticated` checked |
| Role-based channel authorization | ✅ PASS | Admin/counselor/student segmented access |
| Student-to-student isolation | ✅ PASS | Student can only access their own room |

### 8.2 Rate Limiting & Throttling

| Check | Status | Notes |
|---|---|---|
| Per-user connection limit | ✅ PASS | Max 5 connections per user (Redis-backed) |
| Per-user message rate | ✅ PASS | 60 messages/minute sliding window |
| Message content size limit | ❌ MISSING | No cap on `content` field length |
| Bytes-per-second limit | ❌ MISSING | No throughput throttle |

**Finding WS-001 — HIGH:** There is no cap on WebSocket message content length. An attacker (or misbehaving client) can send a single message containing megabytes of text (e.g., 10 MB base64-encoded data). This:
- Passes the message rate limiter (counted as 1 message)
- Gets written to `ChatMessage.content` (unbounded `TextField`)
- Gets broadcast to all room members via Redis channel layer
- Creates Redis pressure proportional to message size

**Recommendation:** Enforce a maximum content length (e.g., 4 KB) in `receive()` before processing.

**Finding WS-002 — MEDIUM:** The `WebSocketSecurityMixin` heartbeat (`send_ping`) is defined but there is no background task or timer implemented to actually call it. The heartbeat is not running unless consumers explicitly start a background coroutine. Stale connections are not proactively detected or closed.

**Finding WS-003 — MEDIUM:** The Redis connection in `ws_security.py` is created via `_redis_client()` on every rate-limit check. This creates a **new Redis connection per message** rather than using a connection pool. For a 60 msg/min rate, this is 60 Redis connections opened and closed per user per minute. This should use a persistent connection pool.

**Finding WS-004 — LOW:** The `DMConsumer` does not validate that `other_user_id` refers to a real, active user at connection time. A counselor can open a DM WebSocket channel to a non-existent user ID and join that group name silently. Only when they send a message does `User.objects.get(pk=self.other_user_id)` raise `DoesNotExist`.

**Finding WS-005 — LOW:** The connection count keys `crm:ws:conn:<user_id>` expire after 24 hours as a safety net. If a worker process crashes without properly calling `disconnect()`, the connection count is never decremented. After a crash, the user's connection count is stuck at 1-N for up to 24 hours, potentially blocking them from reconnecting until the key expires.

### 8.3 Redis Channel Layer

| Check | Status | Notes |
|---|---|---|
| Redis-backed in production | ✅ PASS | `channels_redis.core.RedisChannelLayer` when `REDIS_URL` set |
| In-memory fallback in dev | ✅ PASS | `channels.layers.InMemoryChannelLayer` |
| Capacity limit | ✅ PASS | `capacity=1500` per group |
| Message expiry | ✅ PASS | `expiry=10` seconds |
| Multi-worker broadcast | ✅ PASS | Redis enables cross-worker group messages |

---

## SECTION 9 — CELERY & ASYNC AUDIT

### 9.1 Task Configuration

| Setting | Value | Assessment |
|---|---|---|
| `CELERY_TASK_ACKS_LATE` | `True` | ✅ Correct — requeues on worker crash |
| `CELERY_TASK_REJECT_ON_WORKER_LOST` | `True` | ✅ Correct — prevents silent drop |
| `CELERY_TASK_DEFAULT_RETRY_DELAY` | 60s | ✅ Acceptable |
| `CELERY_TASK_MAX_RETRIES` | 3 | ✅ Acceptable |
| `CELERY_TASK_SOFT_TIME_LIMIT` | 300s | ✅ Good |
| `CELERY_TASK_TIME_LIMIT` | 600s | ✅ Good |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | 1 | ✅ Fair scheduling |
| `CELERY_WORKER_CONCURRENCY` | 2 | ⚠️ May be too low |

### 9.2 Task Inventory

| Task | Queue | Retry | Idempotent | Notes |
|---|---|---|---|---|
| `send_welcome_email_task` | default | 3 attempts | ⚠️ Partial | Resending welcome email on retry is acceptable |
| `send_password_reset_email_task` | default | 3 attempts | ❌ No | Resending reset email sends a new valid link |
| `purge_expired_tokens` | default (Beat) | Default | ✅ Yes | Read-then-delete; safe to retry |
| `cleanup_orphaned_files` | default (Beat) | Default | ✅ Yes | File existence check before delete |
| `archive_old_audit_logs` | default (Beat) | Default | ✅ Yes | Date-bound operation |
| `backup_database` | default (Beat) | Explicit | ⚠️ Partial | Double backup on retry wastes storage |
| `prune_old_backups` | default (Beat) | Default | ✅ Yes | Date-based pruning |
| `log_security_event` | default | Default | ✅ Yes | Creates audit record |

**Finding CELERY-001 — HIGH:** All tasks share a single default queue. There is no queue separation between:
- High-priority tasks (email delivery — user-facing)
- Low-priority tasks (backup, cleanup, archiving)

A large backup task occupying both workers for 10 minutes will delay welcome emails and password resets (user-facing) by the same 10 minutes. **Recommendation:** Define at minimum two queues: `priority` (email, notifications) and `maintenance` (backup, cleanup, archiving).

**Finding CELERY-002 — MEDIUM:** `backup_database` creates a `pg_dump` subprocess using `subprocess.Popen`. If `pg_dump` is not installed on the Railway/Docker image, this silently fails (only an error log). The Docker image's base Python image may not include `pg_dump`. Verify `pg_dump` is installed in the Dockerfile.

**Finding CELERY-003 — MEDIUM:** The `backup_database` task has no dead-letter handling. After 3 retry failures, the task result is stored in Redis backend and silently dropped. Nobody is alerted to the backup failure. A `on_failure` handler should trigger a Sentry alert or email notification.

**Finding CELERY-004 — LOW:** The `backup_database` task reads the full PostgreSQL dump into memory (`file_bytes = f.read()`) before uploading to Supabase. For a large database, this is memory-intensive. A streaming Supabase upload would be preferable.

**Finding CELERY-005 — LOW:** No Celery Flower or equivalent monitoring dashboard is mentioned. Queue depths, task success/failure rates, and worker health are invisible without a monitoring UI.

---

## SECTION 10 — STORAGE AUDIT

### 10.1 Supabase Storage

| Check | Status | Notes |
|---|---|---|
| Upload retry (3 attempts) | ✅ PASS | `_MAX_RETRIES = 3`, `_RETRY_DELAY = 0.5s` |
| Unique path generation (UUID4) | ✅ PASS | `make_unique=True` by default |
| Content-type forwarded | ✅ PASS | Set on upload |
| `upsert: false` | ✅ PASS | Prevents accidental overwrite |
| Delete via service role | ✅ PASS | Service role key used |
| Signed URL support | ✅ PASS | `get_signed_url()` implemented |
| Health probe | ✅ PASS | `supabase_healthy()` lists buckets |

**Finding STORAGE-001 — CRITICAL:** Database backups are stored in the same Supabase bucket (`crm-uploads`) under the `backups/` folder. User-uploaded files are stored under `uploads/`. There is no bucket isolation between sensitive backup data and user content. A misconfigured bucket policy that makes `uploads/` public would also expose backup SQL dumps. Backups must be in a separate, private bucket.

**Finding STORAGE-002 — HIGH:** The `get_public_url()` function is used for both user documents and backups. If the `crm-uploads` bucket is configured as public in Supabase (which is typical for a bucket named `crm-uploads` if the original intent was CDN delivery), then backup SQL dumps at `<SUPABASE_URL>/storage/v1/object/public/crm-uploads/backups/<timestamp>.sql.gz` are publicly accessible by anyone who guesses the URL format. This is a severe data exposure risk.

**Finding STORAGE-003 — MEDIUM:** The `upload_file()` uses `time.sleep(_RETRY_DELAY)` (0.5s) between synchronous retries. This is called from a Django request handler thread. Blocking the ASGI thread for 0.5s per retry (up to 1.5s total wait) for a storage failure degrades concurrent request throughput significantly.

**Finding STORAGE-004 — MEDIUM:** Signed URLs are generated on demand via `get_signed_url()` but there is no evidence they are used for document download in the frontend templates. The `public_url` (which is an unsecured CDN URL) is the primary URL stored and returned. If the bucket is public, all documents (passports, financial records) are accessible to anyone with the URL.

**Finding STORAGE-005 — LOW:** The `cleanup_orphaned_files` task exists but its implementation was not read in full. The effectiveness of orphan detection (Supabase storage files not referenced by any `FileObject` DB record) depends on consistent transactional writes — if the Supabase upload succeeds but the `FileObject.objects.create()` fails, the file is orphaned in storage. The inverse (DB record without storage file) could also occur. Both cases should be handled.

---

## SECTION 11 — TESTING & QA AUDIT

### 11.1 Test Suite Overview

| Test Category | Test Files | Coverage Focus |
|---|---|---|
| Auth | `test_login.py`, `test_logout.py`, `test_password_reset.py` | Login, logout, reset flow |
| Security | `test_permissions.py`, `test_throttles.py`, `test_middleware.py`, `test_mfa_permissions.py`, `test_anomaly_detection.py`, `test_file_scanner.py` | RBAC, throttles, CSP, MFA, anomaly, upload |
| CRM | `test_students.py`, `test_pagination.py`, `test_export.py`, `test_cache_extended.py` | Student CRUD, pagination, CSV export, cache |
| API | `test_health.py`, `test_mfa.py`, `test_storage.py`, `test_uploads.py`, `test_cache.py` | Health endpoint, MFA flow, storage, uploads |
| Async | `test_celery_tasks.py` | Celery task execution |

**Coverage gate:** 70% minimum (`--fail-under=70`).

### 11.2 Testing Findings

**Finding TEST-001 — HIGH:** No WebSocket consumer tests exist. The `ChatConsumer`, `DMConsumer`, and `NotificationConsumer` have zero automated test coverage. WebSocket authorization, message routing, rate limiting, and disconnect handling are all untested. This is the most significant testing gap.

**Finding TEST-002 — HIGH:** No load or stress tests exist. There is no evidence of benchmarking at any user scale. The 70% coverage threshold only covers functional paths, not throughput or concurrency.

**Finding TEST-003 — MEDIUM:** The `conftest.py` globally disables throttling with a very high rate (`10000/second`). This means throttle behavior (which is a security boundary) is never tested in realistic conditions. Dedicated throttle tests should use isolated fixtures that restore real throttle rates.

**Finding TEST-004 — MEDIUM:** The `test_students.py` test exists but its scope was not fully read. IDOR scenarios (counselor A accessing counselor B's students) are a gap in the visible test files.

**Finding TEST-005 — MEDIUM:** The `test_celery_tasks.py` uses the `CELERY_TASK_ALWAYS_EAGER` pattern (implied by the test setup), which executes tasks synchronously. This does not test the actual broker routing, queue separation, or retry behavior under failure conditions.

**Finding TEST-006 — LOW:** No regression tests for the student code generation race condition. The `generate_student_code()` function has a documented race risk but no concurrent test validates the behavior.

**Finding TEST-007 — LOW:** The `--reuse-db` flag in pytest configuration (mentioned in recent commit) can cause tests to run against stale schema state if migrations have changed between runs. While it speeds up CI, it introduces false passes.

### 11.3 Testing Maturity Score

| Dimension | Score | Notes |
|---|---|---|
| Unit test coverage | 6/10 | 70% threshold met |
| Integration test depth | 5/10 | API endpoints covered; WS not covered |
| Security test coverage | 7/10 | Good RBAC, throttle, scanner tests |
| Async/Celery test coverage | 4/10 | Eager-mode only; no real broker tests |
| WebSocket test coverage | 1/10 | No WS tests |
| Load/performance test coverage | 0/10 | Not present |
| **Overall testing maturity** | **4.5/10** | Significant gaps in async and WS |

---

## SECTION 12 — FRONTEND AUDIT

### 12.1 Frontend Architecture

The frontend consists of static HTML files (in directories like `admin_dashboard/code.html`, `counselor_students/code.html`, etc.) served via Django's template system. Pages use Tailwind CSS (CDN) for styling and vanilla JavaScript for interactions. There is no frontend build system — no webpack, Vite, or npm.

### 12.2 Frontend Security Findings

**Finding FE-001 — HIGH:** All frontend JavaScript consumes JWT tokens stored in `localStorage` (inferred from the pattern of `fetch()` calls with `Authorization: Bearer` headers in static HTML files). `localStorage` is accessible to any JavaScript running on the page, making tokens vulnerable to XSS attacks. Industry standard for SPAs is `httpOnly` cookie storage for tokens. However, given the CSP with `'unsafe-inline'`, XSS is partially mitigated.

**Finding FE-002 — HIGH:** The CSP allows `'unsafe-inline'` scripts. Any script injected into the HTML response (via a stored XSS payload in a student name, counselor note, or any user-supplied content rendered in templates) will execute. Django's auto-escaping protects template-rendered content, but JavaScript `innerHTML` assignments in the static HTML files may bypass this protection.

**Finding FE-003 — MEDIUM:** Tailwind CSS is loaded from CDN (`https://cdn.tailwindcss.com`). This CDN dependency means:
1. The application requires an external network request to render correctly
2. CDN availability is a frontend dependency
3. Tailwind CDN's `<script>` tag approach is for development only — it is slow and not suitable for production (Tailwind explicitly states this)

**Finding FE-004 — MEDIUM:** There are 20+ separate HTML "pages" in separate directories, each a standalone file with duplicated `<head>` sections, repeated JavaScript patterns, and independent authentication logic. This monolithic static approach has no component reuse, making maintenance proportionally more expensive as the feature set grows.

**Finding FE-005 — MEDIUM:** Form validation in the frontend is unclear without deep inspection of each HTML file. If client-side validation is the only validation layer for field formats (phone numbers, dates, etc.), server-side serializer validation is the critical backstop. This appears correct — serializers have validators — but the UX may be poor if server-side errors are not user-friendly.

**Finding FE-006 — LOW:** The frontend pages have no accessibility audit (ARIA labels, keyboard navigation, screen reader support). For a SaaS product, WCAG 2.1 AA compliance is a legal requirement in many jurisdictions.

**Finding FE-007 — LOW:** No favicon, manifest, or PWA configuration. The counselor and admin UX could benefit from PWA features (offline capability, installable app) for mobile counselors.

### 12.3 WebSocket Client-Side

Clients connect via `wss://` in production (via Railway TLS). Reconnect logic, connection state management, and offline handling are embedded in individual HTML files with no shared abstraction.

**Finding FE-008 — LOW:** WebSocket reconnection logic (if any) is per-file, not centralized. A network interruption will drop the WS connection, and behavior depends on each page's implementation.

---

## SECTION 13 — DEVOPS & CI/CD AUDIT

### 13.1 GitHub Actions Pipeline

**CI Pipeline (`ci.yml`):**
- `lint` job: Bandit SAST (medium+ severity warns; high severity fails)
- `test` job: Full test suite with PostgreSQL 15 + Redis 7, coverage gate at 70%
- `migrations` job: Migration consistency check + `makemigrations --check`
- `docker` job: Docker build validation

**Security Pipeline (`security.yml`):**
- `pip-audit` job: CVE scanning (daily cron + on push)
- `detect-secrets` job: Secret detection across full git history
- `bandit-deep` job: All-severity Bandit scan (daily cron + on push)

### 13.2 CI/CD Findings

**Finding CICD-001 — CRITICAL:** No staging/pre-production deployment exists in the CI pipeline. After all CI checks pass, there is no deployment step — deploys presumably happen manually or via Railway Git integration. This means:
1. No automated deployment to staging before production
2. No rollback validation
3. No smoke test against a deployed environment

**Finding CICD-002 — HIGH:** The `lint` job runs Bandit but uses `|| true` for the medium/high JSON report — Bandit failures at medium severity do NOT fail the build. Only the second Bandit call (high severity, high confidence) would fail. A medium-severity finding (e.g., `subprocess.Popen` without shell=False, though this is used in the backup task) will not block the merge.

**Finding CICD-003 — HIGH:** The `detect-secrets` job uses `--baseline .secrets.baseline`. If this baseline file doesn't exist or is committed with known secrets already whitelisted, new secrets will not be detected. The scan's effectiveness is gated on baseline hygiene.

**Finding CICD-004 — MEDIUM:** The CI workflow triggers on `responsive-design-test` and `main` branches. Feature branches (e.g., `feature/new-endpoint`) only get CI when a PR to `main` is opened. Developers working on long-lived feature branches get no security scanning feedback until they open a PR.

**Finding CICD-005 — MEDIUM:** No automated deployment to any environment on green CI. Deployment (to Railway) appears to be manual. This removes the repeatability and auditability of production deployments.

**Finding CICD-006 — LOW:** No container image scanning (e.g., Trivy, Snyk) in the pipeline. `pip-audit` checks Python dependencies but not OS-level CVEs in the Docker base image.

**Finding CICD-007 — LOW:** The `--deploy` flag is used in `python manage.py check --deploy 2>&1 || true`. The `|| true` means Django system check failures (e.g., a misconfigured security setting) do not fail the CI job.

---

## SECTION 14 — BUSINESS WORKFLOW AUDIT

### 14.1 Student Lifecycle

```
Lead created → Lead qualified → Student record created (auto-signal on User create)
  → Student profile completed (multi-step form)
  → Schools assigned (counselor selects target schools)
  → Documents uploaded (per school, per category)
  → Applications submitted (tracked via StudentActivity)
  → Follow-ups scheduled (counselor tasks)
  → Notifications sent (in-app + email)
  → Student communicates via chat
  → Application outcome (no model for outcome tracking — gap)
  → Student archived (soft-delete)
```

**Finding BIZ-001 — HIGH:** There is no `Application` model tracking the application outcome (submitted, accepted, rejected, waitlisted, enrolled). `StudentActivity` with type `application_submitted` records an event, but there is no structured status tracking for each `StudentAssignedSchool`. A student can have a school assignment but no way to record "application accepted" or "visa granted." This is a fundamental business workflow gap.

**Finding BIZ-002 — MEDIUM:** The Lead → Student conversion path is not automated. A lead that converts to a student requires manual creation of a `User` with `role=student`, which then auto-creates a `Student` record via signal. There is no API endpoint to "convert lead to student" that atomically:
- Creates the user account
- Links the student to the originating lead
- Moves the lead to `converted` status
- Archives the lead's enquiries/follow-ups

**Finding BIZ-003 — MEDIUM:** Follow-up status `missed` exists in the model but there is no automated mechanism to mark follow-ups as missed when `scheduled_at < now` and status is still `pending`. The Celery Beat schedule does not include a "mark overdue follow-ups" task.

**Finding BIZ-004 — MEDIUM:** No analytics or reporting endpoints exist beyond the dashboard summary counts. Business questions like "which counselor has the highest conversion rate," "what schools are most popular," or "what is the average time from lead to enrollment" cannot be answered from the current API.

**Finding BIZ-005 — LOW:** The `FollowUp.clean()` validation checks that exactly one of lead/enquiry/student is linked. However, `FollowUp.save()` calls `full_clean()` which may raise `ValidationError`. DRF's serializer does not automatically call `full_clean()` on model save — if `FollowUpSerializer` doesn't trigger this validation path, invalid follow-ups could be created via API.

**Finding BIZ-006 — LOW:** The `PriorityItemDismissal` model exists for dismissing priority notifications, but the logic for what constitutes a "priority item" is not visible in the code reviewed. This feature's completeness is unclear.

---

## SECTION 15 — COMPLIANCE & GOVERNANCE

### 15.1 GDPR Assessment

| Requirement | Status | Notes |
|---|---|---|
| Lawful basis for processing | ❌ UNDOCUMENTED | No privacy policy or consent tracking |
| Data minimization | ⚠️ PARTIAL | Student model has 60+ fields; not all may be necessary |
| Right to access (export) | ⚠️ PARTIAL | CSV export exists but not structured as GDPR export |
| Right to erasure | ❌ MISSING | Soft-delete only; PII remains in DB |
| Data retention policy | ⚠️ PARTIAL | 30-day backup retention; no data aging policy |
| Breach notification (72 hours) | ❌ UNDOCUMENTED | No incident response procedure |
| Data processor agreements | ❌ UNDOCUMENTED | Supabase, Railway, Sentry as processors |
| Cross-border transfers | ⚠️ RISK | Railway/Supabase may store data outside EU |

### 15.2 SOC 2 Type II Readiness

| Control | Status | Notes |
|---|---|---|
| Access control (CC6) | ⚠️ PARTIAL | RBAC in place; no access review process |
| Change management (CC8) | ⚠️ PARTIAL | CI/CD exists; no change approval workflow |
| Risk assessment (CC3) | ❌ MISSING | No formal risk register |
| Availability monitoring (A1) | ⚠️ PARTIAL | Health endpoint; no SLA monitoring |
| Audit logging (CC7) | ✅ PASS | `ActivityLog` is comprehensive |
| Incident response (CC7.3) | ❌ MISSING | No formal incident response process |
| Vendor management (CC9) | ❌ MISSING | No DPA with Supabase/Railway/Sentry |
| Encryption (CC6.7) | ✅ PASS | Fernet field encryption, TLS in transit |

**Finding COMPLIANCE-001 — HIGH:** The platform processes student PII (names, passport numbers, financial data, parent information) for what appears to be international students. If any students are EU/UK residents, GDPR applies. There is no consent management, privacy notice, lawful basis documentation, or data protection officer designation.

**Finding COMPLIANCE-002 — HIGH:** No Data Processing Agreements (DPAs) are documented with Supabase (file storage), Railway (infrastructure), Sentry (error telemetry — receives stack traces that may contain PII), or Gmail (SMTP for password reset emails containing user email addresses).

**Finding COMPLIANCE-003 — MEDIUM:** Student passport numbers and income data are encrypted at rest in the database. However, this data is transmitted in API responses to authenticated counselors in plaintext JSON. If a counselor's device is compromised, this PII is exposed. Consider masking PII in API responses (returning `*` for most of passport number except last 3 digits, etc.).

---

## SECTION 16 — SCALABILITY ROADMAP

### 16.1 Current Architecture Capacity Estimate

Based on Railway's default resource allocation, a single Daphne ASGI worker with 2 Celery workers and a single Redis instance can realistically handle:
- **Sustained HTTP:** ~50-100 concurrent requests
- **WebSocket connections:** ~200-500 simultaneous connections (Redis channel layer bottleneck)
- **Database:** ~200 concurrent DB connections (Railway PostgreSQL)
- **Celery throughput:** ~120 tasks/minute (2 workers × 60/min)

### 16.2 Scale Targets

#### 50 Concurrent Users (Current State — Achievable Today)
- **Status:** ✅ Ready
- **Infra:** Single Railway web worker, 2 Celery workers, single Redis
- **DB:** SQLite in dev (fine); PostgreSQL plugin on Railway
- **Actions needed:** None beyond production env vars

#### 500 Concurrent Users

| Component | Change Required |
|---|---|
| Web workers | Scale Railway to 2-3 web worker instances |
| Celery workers | 4-6 workers; separate priority/maintenance queues |
| Redis | Upgrade to larger Redis plan; connection pool |
| Database | Connection pooler (PgBouncer) or Railway PostgreSQL at medium tier |
| Cache | Current TTLs are sufficient |
| WebSocket | Multi-worker Redis channel layer already supports this |
| Storage | Supabase scales automatically |
| **Cost estimate** | ~$150-300/month on Railway |

#### 5,000 Concurrent Users

| Component | Change Required |
|---|---|
| Web workers | Horizontal scaling (5-10 instances) behind Railway load balancer |
| Celery workers | 10-20 workers; Redis Cluster or dedicated broker |
| Database | Read replica for dashboard/reporting; PgBouncer mandatory |
| Cache | Redis Cluster with 3 shards; cache warming strategy |
| WebSocket | Dedicated WS worker pool separate from HTTP workers |
| Storage | Supabase storage CDN (current); file access via signed URLs |
| DB schema | Partitioned `ActivityLog` by month; `FollowUp` by status |
| Search | pg_trgm or dedicated Elasticsearch for student search |
| **Architecture change** | Student code generation must be fixed (race condition) |
| **Cost estimate** | ~$1,500-3,000/month |

#### 50,000 Concurrent Users

| Component | Change Required |
|---|---|
| Architecture | Microservices split: auth service, CRM service, notification service, file service |
| Database | Multi-master or Citus for horizontal sharding |
| Cache | Redis Cluster + application-level cache partitioning |
| Message queue | Dedicated RabbitMQ or Kafka cluster for task routing |
| Storage | Multi-region Supabase or S3-compatible storage with CDN |
| WebSocket | Dedicated WebSocket service (Ably, Pusher, or self-hosted with Erlang) |
| Observability | Full APM (Datadog, New Relic) + distributed tracing |
| CDN | Static assets on CloudFront/Fastly |
| Auth | OAuth2 / OIDC identity provider |
| **Cost estimate** | ~$15,000-30,000/month minimum |

---

## SECTION 17 — INCIDENT RECOVERY REVIEW

### 17.1 Backup & Recovery

| Component | Backup Strategy | Recovery Procedure | Assessment |
|---|---|---|---|
| PostgreSQL | Nightly Celery Beat `pg_dump` → Supabase | Manual restore from `.sql.gz` | ⚠️ UNTESTED |
| Supabase Storage | Supabase internal redundancy | Re-upload from local if available | ❌ No procedure |
| Redis | No backup (ephemeral) | Restart; cache repopulates, WS count resets | ⚠️ ACCEPTABLE |
| Code | GitHub | `git clone` + Railway redeploy | ✅ GOOD |
| Env vars | Railway dashboard | Manual re-entry | ⚠️ SHOULD BE IN VAULT |

**Finding RECOVERY-001 — CRITICAL:** The backup restoration procedure has never been tested (assumed). A backup that cannot be restored is not a backup. A quarterly DR drill — restoring the PostgreSQL dump to a test environment and verifying data integrity — is mandatory.

**Finding RECOVERY-002 — HIGH:** The `pg_dump` command requires `pg_dump` to be installed in the Celery worker's Docker image. Python base images do not include PostgreSQL client tools by default. If `pg_dump` is not installed, every nightly backup task silently fails (logged as error, no alert). Verify the Dockerfile installs `postgresql-client`.

**Finding RECOVERY-003 — HIGH:** Environment variables (secret key, Supabase keys, database URL, encryption key) are stored only in Railway's dashboard. If the Railway project is accidentally deleted, all secrets are lost and must be reconstructed. These should be stored in a vault (Infisical, HashiCorp Vault, or 1Password Teams) with access controls.

**Finding RECOVERY-004 — MEDIUM:** There is no documented rollback procedure for a failed deployment. Railway supports deployment rollback via the dashboard, but there is no documented SOP for when to roll back and how to assess damage from a partial deployment.

**Finding RECOVERY-005 — MEDIUM:** Redis recovery: if Redis crashes, all cached values are lost (acceptable — repopulates from DB), all Celery task results are lost (acceptable — most tasks are `ignore_result=True`), but WebSocket connection counts (`crm:ws:conn:<user_id>`) are lost. If users had active connections when Redis crashed, their connection counters reset to 0. New connections are permitted immediately. This is correct behavior (fail-open) but should be documented.

**Finding RECOVERY-006 — LOW:** The `prune_old_backups` task deletes files older than 30 days. If a catastrophic data corruption event is discovered 45 days after it occurred (e.g., a slow-burning data integrity issue introduced by a migration), backups older than 30 days will already be pruned. Consider a 90-day retention policy with progressive storage (daily → weekly → monthly archives).

---

## SECTION 18 — FINAL SCORECARD

| Category | Score | Grade | Critical Findings | Notes |
|---|---|---|---|---|
| **Security** | 7.4 / 10 | B | AUTH-005 (no account lockout), SECRETS-001/002 (encryption key fallback) | Strong baseline; specific gaps |
| **Infrastructure** | 6.8 / 10 | C+ | INFRA-001 (no staging), INFRA-008 (Beat SPOF) | Railway appropriate; ops gaps |
| **Performance** | 6.5 / 10 | C+ | PERF-001 (memory upload), PERF-004 (ORM objects cached) | Caching good; bottlenecks in uploads |
| **Scalability** | 5.5 / 10 | C | DB-003 (race condition), CELERY-001 (single queue) | Handles 500 users; redesign needed for 5K+ |
| **Observability** | 6.2 / 10 | C+ | OBS-005 (no Celery alerts), OBS-006 (no runbook) | Sentry + audit log; alerting missing |
| **Testing** | 6.0 / 10 | C+ | TEST-001 (no WS tests), TEST-002 (no load tests) | 70% coverage; critical gaps in WS + load |
| **Architecture** | 7.0 / 10 | B- | AUTHZ-001 (editor role broken), BIZ-001 (no Application model) | Clean monolith; business model gaps |
| **Maintainability** | 7.5 / 10 | B | FE-004 (HTML duplication), OBS-008 (untyped audit actions) | Backend well-structured; frontend brittle |
| **DevOps / CI/CD** | 7.0 / 10 | B- | CICD-001 (no staging deploy), CICD-002 (bandit || true) | Good pipeline; deploy automation missing |
| **Operational Maturity** | 5.5 / 10 | C | RECOVERY-001 (backup untested), OBS-006 (no runbook) | Health checks; no incident process |
| **Business Workflow** | 6.5 / 10 | C+ | BIZ-001 (no Application model), BIZ-002 (no lead conversion) | Core flows work; outcome tracking absent |
| **Production Readiness** | **6.5 / 10** | **C+** | — | Conditionally ready for pilot |

---

## SECTION 19 — FINAL VERDICT

### 19.1 Is the System Production-Ready?

**CONDITIONALLY YES** — for a controlled pilot deployment with ≤100 concurrent users and a mature engineering team that understands the gaps. The system is **NOT ready for open SaaS** without addressing the items below.

### 19.2 Suitability for SaaS

The platform is **not yet SaaS-ready** due to:
1. **No multi-tenancy** — one organization's data is not isolated from another's (relevant if the platform is ever sold to multiple institutions)
2. **No self-service onboarding** — new counselors require manual admin intervention
3. **No billing/subscription system**
4. **No GDPR compliance path** (right-to-erasure, consent management)
5. **No application outcome tracking** (fundamental business workflow missing)
6. **Single staging environment gap** — releases are not validated before production

### 19.3 Estimated Maturity Level

| Dimension | Maturity Level |
|---|---|
| Backend Engineering Quality | **Level 3 / 5** — Production-grade patterns in use |
| Security Posture | **Level 3 / 5** — Defense-in-depth; specific gaps remain |
| Operational Maturity | **Level 2 / 5** — Basic ops; no runbook, no staging, no alerting |
| Test Coverage | **Level 2 / 5** — Functional coverage; critical paths untested |
| Business Feature Completeness | **Level 3 / 5** — Core CRM works; outcome tracking absent |
| **Enterprise Readiness** | **Level 2 / 5** — Requires 90-day hardening to reach Level 3 |

### 19.4 Top 10 Priorities (in order)

| Priority | Finding | Impact |
|---|---|---|
| 1 | Fix `FIELD_ENCRYPTION_KEY` to fail hard in production (SECRETS-001) | Data breach risk |
| 2 | Establish staging environment (INFRA-001) | Deployment safety |
| 3 | Promote HSTS to 1 year (TRANSPORT-001) | HTTPS downgrade attacks |
| 4 | Fix student code generation race condition (DB-003) | 500 errors on concurrent creates |
| 5 | Isolate backup bucket in Supabase (STORAGE-001/002) | Backup data exposure |
| 6 | Implement WS message content length cap (WS-001) | DoS via large messages |
| 7 | Add Celery queue separation (CELERY-001) | Email delays under maintenance load |
| 8 | Implement account lockout or CAPTCHA (AUTH-005) | Credential stuffing |
| 9 | Design GDPR erasure path (DB-010, COMPLIANCE-001) | Regulatory risk |
| 10 | Add Celery monitoring + backup failure alerting (OBS-005, CELERY-003) | Silent operational failures |

---

## SECTION 20 — ACTION PLAN

### 20.1 Immediate Priorities (This Week)

| Action | Owner | Effort | Finding |
|---|---|---|---|
| Change `FIELD_ENCRYPTION_KEY` fallback to `raise RuntimeError` in production | Backend | 30 min | SECRETS-001 |
| Verify `FIELD_ENCRYPTION_KEY` in Railway env vars is unique, not the fallback key | DevOps | 30 min | SECRETS-002 |
| Move CI `FIELD_ENCRYPTION_KEY` to GitHub Actions encrypted secret | DevOps | 15 min | SECRETS-004 |
| Cap WebSocket message content to 4 KB in `ChatConsumer.receive()` | Backend | 1 hr | WS-001 |
| Fix student code race condition with DB sequence or retry on `IntegrityError` | Backend | 2 hrs | DB-003 |
| Set `SECURE_HSTS_SECONDS = 31536000` in production (only after confirming HTTPS works end-to-end) | DevOps | 15 min | TRANSPORT-001 |
| Create separate Supabase bucket for backups; update `backup_database` task | Backend | 1 hr | STORAGE-001/002 |

### 20.2 30-Day Roadmap

| Week | Actions |
|---|---|
| **Week 1** | Staging environment on Railway (separate project, same codebase) |
| **Week 1** | Celery queue separation: `priority` queue for email/notifications, `maintenance` for backup/cleanup |
| **Week 1** | Celery Beat health monitoring: heartbeat check + Sentry alert on Beat failure |
| **Week 2** | Account lockout / CAPTCHA after N failed logins (backend + frontend) |
| **Week 2** | MFA requirement for counselor accounts (extend `MFARequiredForAdmin` pattern) |
| **Week 2** | Fix `DashboardViewSet.summary()` to use fewer DB calls (consolidate with cache service) |
| **Week 3** | `Application` model: add `StudentApplicationStatus` to track outcomes per school assignment |
| **Week 3** | Lead → Student conversion API endpoint (atomic operation) |
| **Week 3** | Overdue follow-up auto-marking Celery task |
| **Week 4** | WebSocket consumer tests (at least connect/disconnect/auth/rate-limit flows) |
| **Week 4** | Backup restoration drill to test environment |
| **Week 4** | Store all secrets in Infisical or HashiCorp Vault; sync to Railway |

### 20.3 90-Day Roadmap

| Month | Focus Area | Key Deliverables |
|---|---|---|
| **Month 2** | GDPR compliance | Privacy policy, consent records, right-to-erasure API endpoint, DPAs with Supabase/Railway/Sentry |
| **Month 2** | Observability upgrade | Celery Flower dashboard, queue depth alerts, backup success alerts, on-call runbook v1 |
| **Month 2** | PII hardening | Mask PII in API responses (partial passport, partial phone), remove plaintext from CSV export |
| **Month 3** | Frontend migration | Replace Tailwind CDN with bundled CSS; remove `'unsafe-inline'` from CSP; consolidate HTML pages into shared layout |
| **Month 3** | Performance baseline | Add Django Debug Toolbar in staging; profile dashboard endpoint; establish p95 targets |
| **Month 3** | Load testing | k6 or Locust tests at 100/500/1000 concurrent users; identify first bottleneck |

### 20.4 Scale Roadmap (6-12 Months)

| Milestone | Target | Actions |
|---|---|---|
| **500 users stable** | Month 4-5 | PgBouncer, 4-6 Celery workers, Redis upgrade, monitoring SLO established |
| **1,000 users** | Month 6-7 | PostgreSQL read replica for reports, pg_trgm for student search, Redis Cluster |
| **5,000 users** | Month 9-12 | Separate WS worker pool, database partitioning for ActivityLog, CDN for static assets |

### 20.5 Enterprise Roadmap (12-24 Months)

| Area | Deliverable |
|---|---|
| Multi-tenancy | Organization model + tenant scoping for all queries |
| Authentication | OAuth2/OIDC support (Google Workspace, Microsoft Entra) |
| API versioning | `/api/v1/` prefix; versioned serializers |
| Audit compliance | SOC 2 Type II audit preparation; automated evidence collection |
| Analytics | Dedicated reporting database or BI tool integration |
| Mobile | React Native or Flutter client consuming the existing REST + WS API |
| White-labeling | Per-tenant domain, branding, and configuration |

---

## APPENDIX A — SECURITY FINDING SEVERITY SUMMARY

| ID | Severity | Finding | Status |
|---|---|---|---|
| AUTH-005 | HIGH | No account lockout mechanism | Open |
| AUTHZ-001 | HIGH | Editor role permissions broken/unused | Open |
| SECRETS-001 | HIGH | FIELD_ENCRYPTION_KEY silently falls back in production | Open |
| SECRETS-002 | MEDIUM | Dev fallback encryption key in version control | Open |
| TRANSPORT-001 | HIGH | HSTS at 1 hour — too short for preload | Open |
| TRANSPORT-002 | MEDIUM | CSP allows `'unsafe-inline'` for scripts and styles | Open |
| INPUT-001 | MEDIUM | MIME validation uses filename-based detection in view layer | Open |
| WS-001 | HIGH | No WebSocket message content length cap | Open |
| STORAGE-001 | CRITICAL | Backups in same bucket as user files | Open |
| STORAGE-002 | HIGH | Backup SQL dumps may be publicly accessible via CDN URL | Open |
| DB-003 | HIGH | Student code race condition under concurrent creates | Open |
| INFRA-001 | CRITICAL | No staging environment | Open |
| MFA-001 | MEDIUM | Counselors have no MFA requirement | Open |
| PII-001 | MEDIUM | CSV export unmasked email/phone | Open |
| COMPLIANCE-001 | HIGH | No GDPR consent management or erasure path | Open |
| COMPLIANCE-002 | HIGH | No DPAs with data processors | Open |
| BIZ-001 | HIGH | No Application outcome tracking model | Open |
| TEST-001 | HIGH | No WebSocket consumer tests | Open |
| OBS-005 | HIGH | No Celery/Beat failure alerting | Open |
| RECOVERY-001 | CRITICAL | Backup restoration never tested | Open |

---

*Report generated: 2026-05-23. Next audit recommended: 2026-08-23 (90 days).*

*This document is confidential. Distribute only to engineering leadership and authorized personnel.*
