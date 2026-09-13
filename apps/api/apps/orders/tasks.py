"""Order background jobs."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("murasfood.orders")


@shared_task(name="apps.orders.tasks.expire_unpaid_orders")
def expire_unpaid_orders(older_than_minutes: int = 60, limit: int = 200) -> int:
    """Cancel orders that were never paid, freeing whatever they still hold.

    The backstop, not the main path. Normally an unpaid checkout is resolved by
    the payments layer: the PIX charge expires and the order moves to
    PAYMENT_FAILED. That requires a Payment row, and checkout creates the order
    and the charge in *separate* transactions — so if the provider is down when
    a customer checks out, the order commits with no charge behind it and
    nothing in the payments layer can ever resolve it. It sits in
    PENDING_PAYMENT for good, on the customer's order list and in the merchant's
    dashboard.

    The window is deliberately longer than the PIX one, so this never races the
    payments layer for an order it is already handling.
    """
    from .services import expire_unpaid_orders as expire

    cancelled = expire(older_than_minutes=older_than_minutes, limit=limit)
    if cancelled:
        logger.info(
            "unpaid_orders_expired",
            extra={"event": "orders.expired", "count": cancelled},
        )
    return cancelled
