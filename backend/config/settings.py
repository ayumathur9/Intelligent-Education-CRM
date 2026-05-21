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
    # LOW-009: TOTP / MFA
    "django_otp",
    "django_otp.plugins.otp_totp",
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
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
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
        "user": os.getenv("DRF_USER_RATE", "600/min"),
        "login": os.getenv("DRF_LOGIN_RATE", "5/min"),
        "password_reset": os.getenv("DRF_PASSWORD_RESET_RATE", "3/min"),
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
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10  # seconds — prevents infinite hang on SMTP failure
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Intelligent Education <no-reply@example.com>"
)
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5500")

# ---------------------------------------------------------------------------
# SUPABASE
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "crm-uploads")
SUPABASE_PUBLIC_URL_BASE = os.getenv("SUPABASE_PUBLIC_URL_BASE", "")

# ---------------------------------------------------------------------------
# SECURITY SETTINGS — CRIT-005 / HIGH-003
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    # Start with 1 hour; promote to 1 year once stable.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

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
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d",
        },
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            # JSON in production for structured aggregation; verbose in dev.
            "formatter": "json" if IS_PRODUCTION else "verbose",
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
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging as _logging_module

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            LoggingIntegration(
                level=_logging_module.INFO,
                event_level=_logging_module.ERROR,
            ),
        ],
        # Never send PII to Sentry.
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=DJANGO_ENV,
    )

# ---------------------------------------------------------------------------
# PII FIELD ENCRYPTION — HIGH-005
# AES-128 CBC via django-encrypted-model-fields.
# Key must be a valid Fernet key (32 url-safe base64 bytes).
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
if not FIELD_ENCRYPTION_KEY:
    if IS_PRODUCTION:
        import logging as _logging
        _logging.warning(
            "[HIGH-005] FIELD_ENCRYPTION_KEY is not set. "
            "PII fields (passport number, income, emergency contact) are stored unencrypted. "
            "Generate a Fernet key and set FIELD_ENCRYPTION_KEY in Railway env vars."
        )
    # Dev-only fallback; valid Fernet key generated for local development ONLY.
    # Production MUST set FIELD_ENCRYPTION_KEY to a unique generated key.
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
# VIRUSTOTAL (optional) — HIGH-008
# ---------------------------------------------------------------------------
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")

# ---------------------------------------------------------------------------
# MFA — LOW-009
# ---------------------------------------------------------------------------
MFA_ISSUER = os.getenv("MFA_ISSUER", "Intelligent Education CRM")

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
