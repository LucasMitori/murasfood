"""Background jobs for the accounts domain."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import AuthToken, LoginAttempt

logger = logging.getLogger("murasfood.accounts")

#: Login attempts are kept long enough to investigate an incident, then dropped.
LOGIN_ATTEMPT_RETENTION_DAYS = 90


@shared_task(name="apps.accounts.tasks.purge_expired_tokens")
def purge_expired_tokens() -> dict[str, int]:
    """Delete spent and expired auth tokens, and prune old login attempts.

    Keeping consumed tokens forever grows a table nobody reads and widens the
    blast radius of a database leak.
    """
    now = timezone.now()
    expired, _ = AuthToken.objects.filter(expires_at__lt=now).delete()
    used, _ = AuthToken.objects.filter(used_at__isnull=False).delete()

    cutoff = now - timedelta(days=LOGIN_ATTEMPT_RETENTION_DAYS)
    attempts, _ = LoginAttempt.objects.filter(created_at__lt=cutoff).delete()

    result = {"expired_tokens": expired, "used_tokens": used, "login_attempts": attempts}
    logger.info("auth_token_cleanup", extra={"event": "accounts.cleanup", **result})
    return result
