"""
Production settings.

Fails fast when a required secret is missing rather than silently booting with
an insecure default. The only exception is the container build step, which sets
``DJANGO_COLLECTSTATIC`` to run ``collectstatic`` without real credentials.
"""

from __future__ import annotations

from .base import *
from .base import MIDDLEWARE, env

DEBUG = False
_BUILD_STEP = env.bool("DJANGO_COLLECTSTATIC", default=False)

if not _BUILD_STEP:
    SECRET_KEY = env("DJANGO_SECRET_KEY")  # raises ImproperlyConfigured when unset
    ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# --- Transport security ------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the SPA must be able to read the CSRF token
CSRF_COOKIE_SAMESITE = "Lax"

# --- Static assets -----------------------------------------------------------
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Logging -----------------------------------------------------------------
LOG_FORMAT = "json"
LOGGING["handlers"]["console"]["formatter"] = "json"

# --- Guard rails -------------------------------------------------------------
# The sandbox PIX provider must never confirm real money.
if not _BUILD_STEP and env("PAYMENT_PROVIDER", default="sandbox") == "sandbox":
    import warnings

    warnings.warn(
        "PAYMENT_PROVIDER=sandbox in production: payments will be simulated. "
        "Configure a real PSP before accepting orders.",
        RuntimeWarning,
        stacklevel=1,
    )
