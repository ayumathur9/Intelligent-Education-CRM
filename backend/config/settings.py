from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load `.env` locally; platforms (Railway/Render) inject env vars directly.
load_dotenv(BASE_DIR / ".env")

DJANGO_ENV = os.getenv("DJANGO_ENV", "development").lower()
IS_PRODUCTION = DJANGO_ENV == "production"

# ---------------------------------------------------------------------------
# SECRET KEY — CRIT-004
# Never silently fall back to a weak key in production.
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "[CRIT-004] DJANGO_SECRET_KEY is not set. "
            "Generate one with: python -c \"from django.core.management.utils "
            "import get_random_secret_key; print(get_random_secret_key())\""
        )
    # Local dev only — never reaches production.
    SECRET_KEY = "dev-only-unsafe-secret-key-never-use-in-production"

# ---------------------------------------------------------------------------
# DEBUG — CRIT-005
# Production must always have DJANGO_DEBUG=0.
# ---------------------------------------------------------------------------
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
if IS_PRODUCTION and DEBUG:
    raise RuntimeError(
        "[CRIT-005] DJANGO_DEBUG must be 0 in production. "
        "Set DJANGO_DEBUG=0 in your Railway environment variables."
    )

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    # Django
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # HIGH-005: field-level PII encryption
    "encrypted_model_fields",
    # Local apps
    "apps.common",
    "apps.users",
    "apps.crm",
    "apps.files",
    "apps.audit",
    "apps.notifications",
    "apps.frontend",
    "apps.chat",
]

# ---------------------------------------------------------------------------
# CHANNEL LAYERS — CRIT-002
# Use Redis in production; InMemory only for local dev.
# Redis fix applied in Phase 2 — this block is already structured to
# switch automatically once REDIS_URL is set.
# ---------------------------------------------------------------------------
_REDIS_URL = os.getenv("REDIS_URL", "")
if _REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [_REDIS_URL],
                "capacity": 1500,
                "expiry": 10,
            },
        }
    }
else:
    if IS_PRODUCTION:
        import logging as _logging
        _logging.warning(
            "[CRIT-002] REDIS_URL is not set in production. "
            "WebSocket messages will not broadcast across workers. "
            "Add a Redis plugin to your Railway project."
        )
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # OBS-002: assign X-Request-ID trace header as early as possible.
    "apps.common.middleware.RequestCorrelationMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
    # OBS-003: log 401/403/429 security events after authentication is resolved.
    "apps.common.middleware.SecurityEventLoggingMiddleware",
    # Alert admins on unhandled 500-level exceptions (production only).
    "apps.common.middleware.ServerErrorAlertMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", Path(os.getenv("TEMPLATE_ROOT", str(BASE_DIR.parent)))],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # SEC-CSP: expose per-request nonce to all templates
                "apps.common.context_processors.csp_nonce",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
# Railway sometimes injects non-standard schemes; normalise to postgresql://
if DATABASE_URL and DATABASE_URL.startswith("railwaypostgresql://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("railwaypostgresql://"):]

# Management commands that run at build time and don't touch the database.
_NO_DB_COMMANDS = {"collectstatic", "compress", "compilemessages", "check"}
_running_no_db_command = bool(set(sys.argv) & _NO_DB_COMMANDS)

if not DATABASE_URL:
    if not DEBUG and not _running_no_db_command:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Production deployments require a persistent PostgreSQL database. "
            "On Railway: add the PostgreSQL plugin to your project and redeploy."
        )
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }
else:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL, conn_max_age=600, ssl_require=not DEBUG
        )
    }

# ---------------------------------------------------------------------------
# PASSWORD VALIDATION — MED-006
# All four Django validators are active.
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# STATIC & MEDIA
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model (email login + roles)
AUTH_USER_MODEL = "users.User"

# ---------------------------------------------------------------------------
# CORS — HIGH-007
# Validated at startup in production to prevent silent misconfiguration.
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = False

# ---------------------------------------------------------------------------
# CSRF — HIGH-007 / MED-009
# ---------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# ---------------------------------------------------------------------------
# SESSION SECURITY — HIGH-003
# Sessions expire after 8 hours of inactivity or when browser closes.
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE_SECONDS", "28800"))  # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS-only in production

# ---------------------------------------------------------------------------
# DRF CONFIGURATION
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("DRF_ANON_RATE", "60/min"),
        # MED-2: 600/min was too permissive for an internal tool; lowered to 200/min.
        "user": os.getenv("DRF_USER_RATE", "200/min"),
        "login": os.getenv("DRF_LOGIN_RATE", "5/min"),
        "password_reset": os.getenv("DRF_PASSWORD_RESET_RATE", "3/min"),
        # RL-001: additional scopes
        "upload": os.getenv("DRF_UPLOAD_RATE", "30/min"),
        "burst": os.getenv("DRF_BURST_RATE", "100/min"),
        # RL-002: registration — 10 new accounts per hour per IP
        "register": os.getenv("DRF_REGISTER_RATE", "10/hour"),
    },
    # Never expose Python stack traces in API error responses.
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Intelligent Education CRM API",
    "DESCRIPTION": "Production REST API for Intelligent Education CRM.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
    },
}

# Silence expected system-check warnings that are either intentional or handled
# at the infrastructure layer (Railway terminates SSL, drf_spectacular schema
# warnings are non-functional and affect only API docs generation).
SILENCED_SYSTEM_CHECKS = [
    # drf_spectacular cannot auto-detect serializers on plain APIView subclasses.
    # These are OpenAPI schema warnings only — runtime behaviour is unaffected.
    "drf_spectacular.W001",
    "drf_spectacular.W002",
    # Railway's load balancer handles SSL termination and redirects HTTP→HTTPS.
    # The app itself does not need SECURE_SSL_REDIRECT=True.
    "security.W008",
]

# ---------------------------------------------------------------------------
# JWT — HIGH-004
# Rotate refresh tokens, blacklist on rotation, and track last login.
# ---------------------------------------------------------------------------
JWT_ACCESS_TOKEN_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15"))
JWT_REFRESH_TOKEN_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "7"))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_TOKEN_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,  # HIGH-004: track last login time
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Prevent token type confusion attacks.
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

# ---------------------------------------------------------------------------
# EMAIL (Gmail SMTP)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "0") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10  # seconds — prevents infinite hang on SMTP failure
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Intelligent Education <no-reply@example.com>"
)

# ---------------------------------------------------------------------------
# EMAIL DELIVERABILITY — rate limiting + provider notes
# ---------------------------------------------------------------------------
# Per-address hourly rate limit.  Protects against accidental spam spikes.
# Brute-force welcome/reset emails to the same address are blocked after 10/hr.
EMAIL_RATE_LIMIT_PER_HOUR = int(os.getenv("EMAIL_RATE_LIMIT_PER_HOUR", "10"))

# When EMAIL_BACKEND_PROVIDER=resend, override HOST/PORT/CREDENTIALS automatically.
# Supported: "gmail" (default), "resend", "postmark", "sendgrid", "mailgun"
# To migrate to Resend: set EMAIL_HOST=smtp.resend.com EMAIL_PORT=465
#   EMAIL_USE_SSL=1 EMAIL_USE_TLS=0
#   EMAIL_HOST_USER=resend EMAIL_HOST_PASSWORD=<Resend API key>
#   DEFAULT_FROM_EMAIL="Intelligent Education <no-reply@intelligenteducation.org>"
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://crm.intelligenteducation.org")

# ---------------------------------------------------------------------------
# LOCAL FILE STORAGE
# Files are stored in MEDIA_ROOT on the local filesystem.
# In production, ensure MEDIA_ROOT is on a persistent volume.
# ---------------------------------------------------------------------------
BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", str(BASE_DIR.parent / "backups")))
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

# CRIT-1: Set NGINX_MEDIA_ACCEL=1 in production when Nginx proxies to Django.
# Nginx must have an internal location block:
#   location /protected-media/ { internal; alias /path/to/MEDIA_ROOT/; }
NGINX_MEDIA_ACCEL = os.getenv("NGINX_MEDIA_ACCEL", "0") == "1"

# ---------------------------------------------------------------------------
# SECURITY SETTINGS — CRIT-005 / HIGH-003
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False      # Must be False — JS reads csrftoken cookie for all AJAX requests
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Prevent browsers from sending cookies on cross-site top-level navigations.
    SESSION_COOKIE_SAMESITE = "Strict"

# ---------------------------------------------------------------------------
# FILE UPLOAD SECURITY
# ---------------------------------------------------------------------------
# HIGH-004: Enforce a hard limit on uploaded payload size.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024   # 15 MB global request limit
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB in-memory threshold
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024

ALLOWED_UPLOAD_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}
ALLOWED_UPLOAD_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp",
    "pdf", "doc", "docx", "xls", "xlsx",
    "txt", "csv",
}

# ---------------------------------------------------------------------------
# STRUCTURED LOGGING — MED-004
# JSON format in production for Railway log aggregation and Sentry.
# Human-readable format in development.
# Sensitive fields are never logged (passwords, tokens, keys).
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "request_id": {
            "()": "apps.common.middleware.RequestIdFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d %(request_id)s",
        },
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s [%(request_id)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            # JSON in production for structured aggregation; verbose in dev.
            "formatter": "json" if IS_PRODUCTION else "verbose",
            "filters": ["request_id"],
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING" if IS_PRODUCTION else "DEBUG",
    },
    "loggers": {
        # Django security events always logged at ERROR+ in production.
        "django.security": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Our application code.
        "apps": {
            "handlers": ["console"],
            "level": "INFO" if IS_PRODUCTION else "DEBUG",
            "propagate": False,
        },
        # Suppress noisy third-party loggers in production.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING" if IS_PRODUCTION else "DEBUG",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# SENTRY ERROR TRACKING — LOW-011
# Automatically enabled when SENTRY_DSN env var is provided.
# ---------------------------------------------------------------------------
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk  # type: ignore[import]
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    import logging as _logging_module

    # OBS-001: full Sentry integration with Celery, Redis, and release tracking.
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
            LoggingIntegration(
                level=_logging_module.INFO,
                event_level=_logging_module.ERROR,
            ),
        ],
        # Never send PII to Sentry.
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        environment=DJANGO_ENV,
        release=os.getenv("RAILWAY_DEPLOYMENT_ID") or os.getenv("GIT_SHA", "local"),
        before_send=lambda event, hint: _sentry_scrub_pii(event, hint),
    )

    def _sentry_scrub_pii(event, hint):
        """Strip PII fields from Sentry events before transmission."""
        _REDACT = {"password", "token", "secret", "passport_number",
                   "father_annual_income", "mother_annual_income",
                   "emergency_mobile", "emergency_email"}
        request = event.get("request", {})
        data = request.get("data", {})
        if isinstance(data, dict):
            for key in list(data):
                if any(p in key.lower() for p in _REDACT):
                    data[key] = "[Filtered]"
        return event

# ---------------------------------------------------------------------------
# PII FIELD ENCRYPTION — HIGH-005
# AES-128 CBC via django-encrypted-model-fields.
# Key must be a valid Fernet key (32 url-safe base64 bytes).
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
if not FIELD_ENCRYPTION_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "[HIGH-005] FIELD_ENCRYPTION_KEY is not set. "
            "PII fields (passport number, income, emergency contact) would be stored unencrypted. "
            "Generate a key: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and set FIELD_ENCRYPTION_KEY in your environment variables."
        )
    # Dev-only fallback; valid Fernet key for local development ONLY.
    FIELD_ENCRYPTION_KEY = "NpY4Ttx1ztyDl--COHI7o5b2X3aj3SFX_40AGe2KjlU="

# ---------------------------------------------------------------------------
# REDIS CACHE BACKEND — INFRA-003
# Shared cache used for: dashboard summaries, student lists, unread notifications.
# Falls back to LocMemCache when REDIS_URL is not set (dev/test).
# ---------------------------------------------------------------------------
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _REDIS_URL,
            "OPTIONS": {
                "socket_connect_timeout": 3,
                "socket_timeout": 3,
            },
            "KEY_PREFIX": "crm",
            "TIMEOUT": 300,  # 5-minute default TTL
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "crm-local",
        }
    }

# Cache TTL constants (seconds) — import from settings where needed.
CACHE_TTL_DASHBOARD = int(os.getenv("CACHE_TTL_DASHBOARD", "120"))   # 2 min
CACHE_TTL_STUDENT_LIST = int(os.getenv("CACHE_TTL_STUDENT_LIST", "60"))  # 1 min
CACHE_TTL_SCHOOL_LIST = int(os.getenv("CACHE_TTL_SCHOOL_LIST", "300"))  # 5 min

# ---------------------------------------------------------------------------
# CELERY — ASYNC-001
# Broker and result backend both use Redis when available.
# Falls back gracefully to memory in development (no broker = sync execution).
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = _REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = _REDIS_URL or "cache+memory://"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE  # matches Django TIME_ZONE
CELERY_ENABLE_UTC = True

# Task reliability settings.
CELERY_TASK_ACKS_LATE = True              # re-queue on worker crash
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # don't silently drop tasks
CELERY_TASK_DEFAULT_RETRY_DELAY = 60      # seconds between automatic retries
CELERY_TASK_MAX_RETRIES = 3               # give up after 3 attempts

# Timeouts — prevents runaway tasks from blocking workers.
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_SOFT_TIMEOUT", "300"))   # 5 min
CELERY_TASK_TIME_LIMIT      = int(os.getenv("CELERY_HARD_TIMEOUT", "600"))   # 10 min

# Worker concurrency (Railway: set CELERY_WORKER_CONCURRENCY env var).
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))
CELERY_WORKER_PREFETCH_MULTIPLIER = 1     # fair scheduling

# Task routing — define separate queues for different task classes.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES_DEFAULT_EXCHANGE = "default"

# Email tasks run on a dedicated queue with conservative concurrency so a spike
# of outbound mail does not starve other Celery workers.
CELERY_TASK_ROUTES = {
    "apps.common.email_tasks.*": {"queue": "email"},
    "apps.notifications.tasks.*": {"queue": "default"},
}

# Beat schedule for periodic maintenance tasks.
from celery.schedules import crontab as _crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {
    # Daily at 03:00 IST: purge expired JWT tokens from the blacklist table.
    "purge-expired-tokens": {
        "task": "apps.users.tasks.purge_expired_tokens",
        "schedule": _crontab(hour=3, minute=0),
    },
    # Daily: clean up expired password reset tokens.
    "cleanup-expired-reset-tokens": {
        "task": "apps.users.tasks.cleanup_expired_reset_tokens",
        "schedule": _crontab(hour=3, minute=15),
    },
    # Every midnight: rotate and archive old audit log entries.
    "archive-old-audit-logs": {
        "task": "apps.audit.tasks.archive_old_audit_logs",
        "schedule": _crontab(hour=0, minute=30),
    },
    # RECOVERY-001: Nightly database backup at 02:00 UTC.
    "nightly-db-backup": {
        "task": "apps.common.tasks.backup_database",
        "schedule": _crontab(hour=2, minute=0),
    },
    # RECOVERY-001: Weekly backup pruning — delete local files older than BACKUP_RETENTION_DAYS.
    "weekly-prune-backups": {
        "task": "apps.common.tasks.prune_old_backups",
        "schedule": _crontab(hour=3, minute=30, day_of_week=0),  # Sunday 03:30
    },
    # LOW: Weekly orphaned file cleanup — remove files without a FileObject record.
    "weekly-cleanup-orphaned-files": {
        "task": "apps.files.tasks.cleanup_orphaned_files",
        "schedule": _crontab(hour=4, minute=0, day_of_week=0),  # Sunday 04:00
    },
    # SEC-FALLBACK: Daily prune of DB-backed login failure records.
    "daily-prune-login-failures": {
        "task": "apps.audit.tasks.prune_login_failures",
        "schedule": _crontab(hour=3, minute=45),
    },
    # Weekly (Monday 08:00 IST): profile-completion reminder to students with missing fields.
    "weekly-profile-reminders": {
        "task": "apps.common.tasks.send_weekly_profile_reminders",
        "schedule": _crontab(hour=8, minute=0, day_of_week=1),
    },
}

# ---------------------------------------------------------------------------
# VIRUSTOTAL (optional) — HIGH-008
# ---------------------------------------------------------------------------
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")

# ---------------------------------------------------------------------------
# WEBSOCKET SECURITY — WS-001
# ---------------------------------------------------------------------------
WS_MAX_CONNECTIONS_PER_USER = int(os.getenv("WS_MAX_CONNECTIONS_PER_USER", "5"))
WS_MAX_MESSAGES_PER_MINUTE = int(os.getenv("WS_MAX_MESSAGES_PER_MINUTE", "60"))
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))
WS_MAX_MESSAGE_BYTES = int(os.getenv("WS_MAX_MESSAGE_BYTES", str(64 * 1024)))  # 64 KB

# ---------------------------------------------------------------------------
# ACCOUNT LOCKOUT — SEC-002
# Per-email lockout (complement to per-IP lockout in throttles.py).
# ---------------------------------------------------------------------------
ACCOUNT_LOCKOUT_THRESHOLD = int(os.getenv("ACCOUNT_LOCKOUT_THRESHOLD", "10"))
ACCOUNT_LOCKOUT_SECONDS = int(os.getenv("ACCOUNT_LOCKOUT_SECONDS", "900"))  # 15 min

# ---------------------------------------------------------------------------
# MFA — LOW-009 / HIGH-1
# ---------------------------------------------------------------------------
MFA_ISSUER = os.getenv("MFA_ISSUER", "Intelligent Education CRM")

# ---------------------------------------------------------------------------
# EMAIL VERIFICATION — HIGH-2
# When True, users must verify their email before they can log in.
# For internal deployments with <50 known users, set to False to allow
# admin-created accounts to skip verification.
# ---------------------------------------------------------------------------
EMAIL_VERIFICATION_REQUIRED = os.getenv("EMAIL_VERIFICATION_REQUIRED", "0") == "1"

# ---------------------------------------------------------------------------
# ORPHANED FILE CLEANUP — LOW
# ---------------------------------------------------------------------------
ORPHAN_FILE_RETENTION_DAYS = int(os.getenv("ORPHAN_FILE_RETENTION_DAYS", "7"))

# ---------------------------------------------------------------------------
# PRODUCTION STARTUP VALIDATION — CRIT-001 / HIGH-007 / MED-009
# Fail loudly at startup if required env vars are missing in production.
# This prevents silent misconfiguration that only surfaces at runtime.
# ---------------------------------------------------------------------------
if IS_PRODUCTION and not _running_no_db_command:
    _missing: list[str] = []

    # Core security
    if not os.getenv("DJANGO_SECRET_KEY"):
        _missing.append("DJANGO_SECRET_KEY")

    # CORS — HIGH-007: empty list means all cross-origin requests are blocked
    # or fall through to defaults depending on corsheaders version.
    if not CORS_ALLOWED_ORIGINS:
        _missing.append("DJANGO_CORS_ALLOWED_ORIGINS")

    # CSRF — MED-009: empty list means CSRF protection fails for POST forms
    # from the production domain.
    if not CSRF_TRUSTED_ORIGINS:
        _missing.append("DJANGO_CSRF_TRUSTED_ORIGINS")

    # Email (non-fatal warning — app works without email)
    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        import logging as _logging
        _logging.warning(
            "[CRIT-001] EMAIL_HOST_USER or EMAIL_HOST_PASSWORD not set. "
            "Email features (password reset, welcome emails) will be disabled."
        )

    if _missing:
        raise RuntimeError(
            f"[CRIT-001] Missing required environment variables for production: "
            f"{', '.join(_missing)}. "
            f"Set these in your Railway environment variables before deploying."
        )
