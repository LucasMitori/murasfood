"""Payment background jobs."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("murasfood.payments")


@shared_task(name="apps.payments.tasks.expire_stale_payments")
def expire_stale_payments() -> int:
    """Expire PIX charges whose window has closed.

    The paired order transition releases the reserved stock, so an unpaid
    checkout cannot hold inventory indefinitely.
    """
    from .services import expire_open_payments

    return expire_open_payments()


@shared_task(name="apps.payments.tasks.reconcile_pending_payments")
def reconcile_pending_payments(older_than_minutes: int = 10, limit: int = 100) -> int:
    """Re-query the provider for payments still open after a webhook should have arrived.

    Webhooks get lost — networks fail, deploys restart processes mid-request.
    Polling is the backstop that keeps a paid order from sitting unfulfilled.
    """
    from .constants import OPEN_PAYMENT_STATUSES
    from .models import Payment
    from .services import reconcile_payment

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    stale = Payment.objects.filter(
        status__in=OPEN_PAYMENT_STATUSES, created_at__lt=cutoff
    ).order_by("created_at")[:limit]

    checked = 0
    for payment in list(stale):
        reconcile_payment(payment)
        checked += 1

    if checked:
        logger.info("payments_reconciled", extra={"event": "payments.reconciled", "count": checked})
    return checked
