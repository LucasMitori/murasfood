"""
Shared Django settings for every environment.

Environment-specific modules (``development``, ``production``, ``test``) import
everything from here and override only what differs. No secret, credential or
merchant-specific value may be hard-coded in this file — everything comes from
the environment (see ``.env.example``).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ

# --- Paths -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# `.env` lives at the repository root in Docker; also honour an app-local copy.
for candidate in (BASE_DIR / ".env", BASE_DIR.parent.parent / ".env"):
    if candidate.exists():
        environ.Env.read_env(str(candidate))
        break

# --- Core --------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-development-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# auth.W004 warns that USERNAME_FIELD is not globally unique. That is deliberate:
# email is unique *per tenant* (see the constraints on accounts.User), and
# `apps.accounts.backends.TenantModelBackend` resolves the ambiguity safely.
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --- Applications ------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

# Domain modules. Order matters only for migration dependencies.
LOCAL_APPS = [
    "apps.common",
    "apps.tenants",
    "apps.accounts",
    "apps.catalog",
    "apps.media",
    "apps.pricing",
    "apps.inventory",
    "apps.promotions",
    "apps.cart",
    "apps.delivery",
    "apps.orders",
    "apps.payments",
    "apps.notifications",
    "apps.finance",
    "apps.reports",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# --- Middleware --------------------------------------------------------------
MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.TenantMiddleware",
    "apps.common.middleware.AccessLogMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ----------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://murasfood:murasfood@localhost:5432/murasfood",
    )
}
DATABASES["default"].setdefault("CONN_MAX_AGE", env.int("DB_CONN_MAX_AGE", default=60))
DATABASES["default"]["ATOMIC_REQUESTS"] = False

# --- Cache / Celery ----------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
# Only meaningful in eager mode. Tests want failures to surface; a developer
# running a management command does not want a missing SMTP server to abort the
# business operation that queued the email.
CELERY_TASK_EAGER_PROPAGATES = env.bool("CELERY_TASK_EAGER_PROPAGATES", default=False)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = env("DJANGO_TIME_ZONE", default="America/Sao_Paulo")

CELERY_BEAT_SCHEDULE = {
    "release-expired-stock-reservations": {
        "task": "apps.inventory.tasks.release_expired_reservations",
        "schedule": 60.0,
    },
    "expire-stale-payments": {
        "task": "apps.payments.tasks.expire_stale_payments",
        "schedule": 300.0,
    },
    "purge-expired-auth-tokens": {
        "task": "apps.accounts.tasks.purge_expired_tokens",
        "schedule": 3600.0,
    },
    "retry-failed-emails": {
        "task": "apps.notifications.tasks.retry_failed_emails",
        "schedule": 600.0,
    },
}

# --- Authentication ----------------------------------------------------------
# Tenant-aware backend: email is unique per tenant, not globally.
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.TenantModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# PBKDF2 is Django's default and needs no native dependency. To upgrade to
# Argon2, add `argon2-cffi` to requirements and move the Argon2 hasher to the
# top: existing hashes are transparently re-hashed on the next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# --- Internationalisation ----------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("pt-br", "Português (Brasil)"),
    ("en", "English"),
    ("es", "Español"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Static / media ----------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# --- REST framework ----------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "login": "10/min",
        "register": "10/hour",
        "password_reset": "5/hour",
        "email_verification": "10/hour",
        "checkout": "30/hour",
        "search": "120/min",
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=14)
    ),
    # Rotation + blacklist gives us real revocation instead of long-lived bearers.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SECRET", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.TokenObtainPairSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MurasFood API",
    "DESCRIPTION": (
        "White-label local commerce platform. Multi-tenant: every request is "
        "scoped to a tenant resolved from the authenticated user, the "
        "`X-Tenant` header or the request subdomain."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "apps.orders.constants.OrderStatus.choices",
        "PaymentStatusEnum": "apps.payments.constants.PaymentStatus.choices",
    },
}

# --- CORS / CSRF -------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant",
    "x-request-id",
    # The anonymous cart is addressed by this header. Omitting it does not
    # merely hide something — the preflight rejects the whole request, so every
    # cart call failed as soon as the client had a token to send.
    "x-cart-token",
    "idempotency-key",
    "accept-language",
)

# Response headers the browser is allowed to hand to JavaScript.
#
# A cross-origin response exposes only the handful of "safelisted" headers by
# default; anything else is readable by the network tab but invisible to
# `fetch`. Without this the storefront could never read the cart token it is
# sent, so every anonymous cart was orphaned the moment the page reloaded.
CORS_EXPOSE_HEADERS = [
    "X-Cart-Token",
    "X-Request-Id",
    "X-Idempotent-Replay",
]

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"])

# --- Object storage ----------------------------------------------------------
# An empty S3_ENDPOINT selects the local filesystem backend (development only).
STORAGE_BACKEND = env("STORAGE_BACKEND", default="auto")
S3_ENDPOINT = env("S3_ENDPOINT", default="")
S3_PUBLIC_ENDPOINT = env("S3_PUBLIC_ENDPOINT", default=S3_ENDPOINT)
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_BUCKET = env("S3_BUCKET", default="murasfood-media")
S3_REGION = env("S3_REGION", default="us-east-1")
S3_SIGNED_URL_TTL_SECONDS = env.int("S3_SIGNED_URL_TTL_SECONDS", default=900)

# Upload guard rails, enforced in apps.media.services.
MEDIA_MAX_UPLOAD_BYTES = env.int("MEDIA_MAX_UPLOAD_BYTES", default=10 * 1024 * 1024)
MEDIA_ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/avif"]
MEDIA_ALLOWED_DOCUMENT_TYPES = ["application/pdf"]
MEDIA_IMAGE_DERIVATIVES = {
    "thumbnail": 160,
    "small": 320,
    "medium": 640,
    "large": 1280,
}

# --- Email -------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("SMTP_HOST", default="localhost")
EMAIL_PORT = env.int("SMTP_PORT", default=1025)
EMAIL_HOST_USER = env("SMTP_USERNAME", default="")
EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("SMTP_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("SMTP_FROM_EMAIL", default="no-reply@example.test")
EMAIL_FROM_NAME = env("SMTP_FROM_NAME", default="MurasFood")
EMAIL_MAX_ATTEMPTS = env.int("EMAIL_MAX_ATTEMPTS", default=5)

# --- Payments ----------------------------------------------------------------
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="sandbox")
PAYMENT_API_KEY = env("PAYMENT_API_KEY", default="")
PAYMENT_API_BASE_URL = env("PAYMENT_API_BASE_URL", default="")
PAYMENT_WEBHOOK_SECRET = env("PAYMENT_WEBHOOK_SECRET", default="")
PAYMENT_PIX_EXPIRATION_SECONDS = env.int("PAYMENT_PIX_EXPIRATION_SECONDS", default=1800)

# --- Public URLs -------------------------------------------------------------
PUBLIC_APP_URL = env("PUBLIC_APP_URL", default="http://localhost:3000")
PUBLIC_API_URL = env("PUBLIC_API_URL", default="http://localhost:8000")

# --- Domain policy -----------------------------------------------------------
# Stock reservations are released automatically when a payment is not completed
# within this window, so abandoned checkouts cannot lock inventory forever.
STOCK_RESERVATION_TTL_SECONDS = env.int("STOCK_RESERVATION_TTL_SECONDS", default=1800)
IDEMPOTENCY_KEY_TTL_SECONDS = env.int("IDEMPOTENCY_KEY_TTL_SECONDS", default=24 * 3600)
LOGIN_MAX_FAILED_ATTEMPTS = env.int("LOGIN_MAX_FAILED_ATTEMPTS", default=10)
LOGIN_LOCKOUT_SECONDS = env.int("LOGIN_LOCKOUT_SECONDS", default=900)

# --- Logging -----------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_FORMAT = env("LOG_FORMAT", default="console")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging.RequestIDFilter"},
    },
    "formatters": {
        "json": {"()": "apps.common.logging.JSONFormatter"},
        "console": {
            "format": "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
        "murasfood": {"level": LOG_LEVEL, "propagate": True},
    },
}
