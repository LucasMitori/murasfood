"""Inventory background jobs."""

from __future__ import annotations

import logging

from celery import shared_task

from .services import expire_stale_reservations

logger = logging.getLogger("murasfood.inventory")


@shared_task(name="apps.inventory.tasks.release_expired_reservations")
def release_expired_reservations() -> int:
    """Free stock held by checkouts that were never paid.

    Scheduled every minute. The window itself is ``STOCK_RESERVATION_TTL_SECONDS``
    and should comfortably exceed how long a customer needs to pay a PIX charge.
    """
    return expire_stale_reservations()


@shared_task(name="apps.inventory.tasks.notify_low_stock")
def notify_low_stock(tenant_id: str) -> int:
    """Alert staff about items that need restocking."""
    from apps.notifications.services import queue_transactional_email
    from apps.tenants.models import Tenant

    from .services import low_stock_items

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return 0

    items = low_stock_items(tenant_id, limit=50)
    if not items:
        return 0

    queue_transactional_email(
        tenant=tenant,
        template_key="inventory.low_stock",
        recipient=tenant.support_email,
        context={
            "count": len(items),
            "items": [
                {
                    "name": item.product.name,
                    "sku": item.product.sku,
                    "available": str(item.available_quantity),
                }
                for item in items
            ],
        },
    )
    logger.info("low_stock_alert_sent", extra={"event": "inventory.low_stock", "count": len(items)})
    return len(items)
