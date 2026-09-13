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


@shared_task(name="apps.inventory.tasks.notify_low_stock_all_tenants")
def notify_low_stock_all_tenants() -> int:
    """Run the low-stock alert for every active shop.

    `notify_low_stock` takes a tenant, which a beat entry cannot supply — which
    is why the alert had never run for anybody. This is the fan-out that gives
    it something to be scheduled as.

    Each shop is dispatched as its own task so one tenant's failure does not
    take the rest of the run down with it.
    """
    from apps.tenants.models import Tenant, TenantStatus

    dispatched = 0
    # The same condition as `Tenant.is_operational`: a suspended shop should not
    # be sent restocking advice.
    operational = Tenant.objects.filter(is_active=True, status=TenantStatus.ACTIVE)
    for tenant_id in operational.values_list("pk", flat=True):
        notify_low_stock.delay(str(tenant_id))
        dispatched += 1
    return dispatched


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
