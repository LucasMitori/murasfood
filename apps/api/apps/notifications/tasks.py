"""Notification background jobs."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import EmailLog, EmailStatus

logger = logging.getLogger("murasfood.notifications")


@shared_task(
    name="apps.notifications.tasks.send_email",
    bind=True,
    max_retries=4,
    # Exponential backoff with jitter: a temporarily unreachable SMTP server
    # should not be hammered by every queued email at once.
    retry_backoff=30,
    retry_backoff_max=900,
    retry_jitter=True,
)
def send_email(self, log_id: str, context: dict[str, Any] | None = None) -> bool:
    """Render and deliver one queued email."""
    from .services import deliver_email

    log = EmailLog.objects.select_related("tenant").filter(pk=log_id).first()
    if log is None or log.status == EmailStatus.SENT:
        return False

    try:
        return deliver_email(log, context or {})
    except Exception as exc:
        if self.request.retries >= settings.EMAIL_MAX_ATTEMPTS - 1:
            EmailLog.objects.filter(pk=log_id).update(status=EmailStatus.FAILED)
            logger.error(
                "email_delivery_gave_up",
                extra={"event": "notifications.gave_up", "log_id": str(log_id)},
            )
            return False
        raise self.retry(exc=exc) from exc


@shared_task(name="apps.notifications.tasks.retry_failed_emails")
def retry_failed_emails(limit: int = 100) -> int:
    """Re-queue emails that failed transiently.

    Runs on a schedule so a provider outage recovers on its own instead of
    silently dropping order confirmations.
    """
    cutoff = timezone.now() - timedelta(minutes=5)
    stuck = EmailLog.objects.filter(
        status=EmailStatus.RETRYING,
        attempts__lt=settings.EMAIL_MAX_ATTEMPTS,
        updated_at__lt=cutoff,
    ).order_by("created_at")[:limit]

    requeued = 0
    for log in list(stuck):
        send_email.delay(str(log.pk), {})
        requeued += 1

    if requeued:
        logger.info("emails_requeued", extra={"event": "notifications.requeued", "count": requeued})
    return requeued


@shared_task(name="apps.notifications.tasks.cleanup_old_notifications")
def cleanup_old_notifications(retention_days: int = 180) -> int:
    """Drop read notifications past the retention window (LGPD data minimisation)."""
    from .models import Notification, NotificationStatus

    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = Notification.objects.filter(
        status=NotificationStatus.READ, created_at__lt=cutoff
    ).delete()
    return deleted
