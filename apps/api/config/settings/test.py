"""
Test settings.

Runs against PostgreSQL when ``DATABASE_URL`` is set (CI and Docker) and falls
back to an in-memory SQLite database otherwise, so ``pytest`` works on a bare
checkout without any running services. Code that depends on PostgreSQL-only
features must degrade gracefully — see ``apps.catalog.search``.
"""

from __future__ import annotations

from .base import *
from .base import env

DEBUG = False
SECRET_KEY = "test-secret-key-not-used-anywhere-else"
ALLOWED_HOSTS = ["*", "testserver"]

if not env("DATABASE_URL", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            "TEST": {"NAME": ":memory:"},
        }
    }

# Hash passwords with the cheapest available hasher: the suite creates many users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "murasfood-test",
    }
}

# Tasks execute inline so tests can assert on their side effects directly.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Deterministic, offline payment provider.
PAYMENT_PROVIDER = "sandbox"
PAYMENT_WEBHOOK_SECRET = "test-webhook-secret"

# Local filesystem storage: no network calls from the suite.
STORAGE_BACKEND = "local"
S3_ENDPOINT = ""

# Throttling would make tests order-dependent and flaky.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": (),
    "DEFAULT_THROTTLE_RATES": {},
}

LOGGING["root"]["level"] = "ERROR"
