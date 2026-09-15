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


@shared_task(name="apps.inventory.tasks.notify_restocked")
def notify_restocked(product_id: str) -> int:
    """Tell everyone waiting that a product is sellable again.

    Re-checks availability before sending. The task is queued on commit of the
    stock write, but it runs later — and in between, someone may well have
    bought the two units that came in. Emailing "it's back" about something that
    is gone again is worse than silence.

    Each alert is stamped as it is sent, inside the same transaction as the
    queueing, so a worker that dies mid-batch does not re-email the people it
    already reached.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.catalog.models import Product
    from apps.notifications.services import queue_transactional_email

    from .models import InventoryItem, RestockAlert

    product = Product.objects.select_related("tenant").filter(pk=product_id).first()
    if product is None:
        return 0

    item = InventoryItem.objects.filter(product=product).first()
    if item is not None and item.track_stock and item.available_quantity <= 0:
        logger.info(
            "restock_notice_skipped",
            extra={"event": "inventory.restock_gone", "product_id": str(product_id)},
        )
        return 0

    alerts = list(
        RestockAlert.objects.select_related("customer")
        .filter(product=product, notified_at__isnull=True)
        .order_by("created_at")
    )
    if not alerts:
        return 0

    # Checked once, before anything is stamped.
    #
    # `queue_transactional_email` answers `None` both for "already queued" and
    # for "no such template", and the caller cannot tell them apart. Stamping
    # first and discovering the second afterwards is how the first run of this
    # task marked a waiting shopper as notified and sent them nothing — the
    # template had never been seeded for the tenant. Establishing the template
    # exists up front makes a `None` inside the loop mean only the harmless one.
    from apps.notifications.models import EmailTemplate

    if not EmailTemplate.objects.filter(
        tenant=product.tenant, key="inventory.restocked", is_active=True
    ).exists():
        logger.error(
            "restock_template_missing",
            extra={
                "event": "inventory.restock_no_template",
                "tenant_id": str(product.tenant_id),
                "waiting": len(alerts),
            },
        )
        return 0

    sent = 0
    for alert in alerts:
        recipient = alert.recipient
        if not recipient:
            continue

        with transaction.atomic():
            stamped = RestockAlert.objects.filter(pk=alert.pk, notified_at__isnull=True).update(
                notified_at=timezone.now()
            )
            # Another worker got there first. Not an error — just not ours.
            if not stamped:
                continue

            queue_transactional_email(
                tenant=product.tenant,
                template_key="inventory.restocked",
                recipient=recipient,
                user=alert.customer,
                locale=alert.locale or None,
                context={
                    "first_name": (alert.customer.first_name if alert.customer_id else "") or "",
                    "product_name": product.name,
                    "product_url": f"/products/{product.slug}",
                },
                related_type="product",
                related_id=str(product.pk),
                # One notice per person per restock. The timestamp is what makes
                # a later restock of the same product a different message.
                idempotency_key=f"restock:{product.pk}:{alert.pk}:{timezone.now():%Y%m%d%H}",
            )
            sent += 1

    logger.info(
        "restock_notices_queued",
        extra={"event": "inventory.restocked", "product_id": str(product_id), "count": sent},
    )
    return sent
