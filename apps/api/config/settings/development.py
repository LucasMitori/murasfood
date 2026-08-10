"""Local development settings. Never use these in production."""

from .base import *
from .base import BASE_DIR, INSTALLED_APPS, env  # noqa: F401

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

# Convenience only: the browsable API makes manual exploration much faster.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# Mailpit captures everything; no mail ever leaves the machine.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Redis is optional locally — fall back to an in-process cache when absent.
if env.bool("USE_LOCAL_MEMORY_CACHE", default=False):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "murasfood-dev",
        }
    }
