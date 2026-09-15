"""
Inventory operations.

This module is where the concurrency guarantees live (spec §50). Two customers
buying the last unit at the same moment must not both succeed, so every write
path:

1. opens a transaction,
2. re-reads the row with ``SELECT … FOR UPDATE``,
3. re-checks availability *inside* the lock,
4. writes both the new level and its movement row.

Checking availability before taking the lock — or trusting a value the frontend
sent — is exactly the race this design exists to prevent.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import record_audit
from apps.common.exceptions import ConflictError, InsufficientStockError
from apps.common.money import quantize_quantity

from .models import (
    InventoryItem,
    MovementType,
    ReservationStatus,
    RestockAlert,
    StockMovement,
    StockReservation,
)

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.catalog.models import Product
    from apps.orders.models import Order
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.inventory")


class NegativeStockError(ConflictError):
    default_detail = _("This change would drive stock negative.")
    default_code = "NEGATIVE_STOCK"


def get_or_create_item(product: Product) -> InventoryItem:
    """Fetch the stock record for a product, creating an empty one if needed."""
    item, _created = InventoryItem.objects.get_or_create(
        product=product, defaults={"tenant_id": product.tenant_id}
    )
    return item


def _allows_backorder(tenant: Tenant) -> bool:
    settings_row = getattr(tenant, "settings", None)
    return bool(settings_row and settings_row.allow_backorder)


def _write_movement(
    *,
    item: InventoryItem,
    movement_type: str,
    quantity: Decimal,
    actor: User | None = None,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
) -> StockMovement:
    return StockMovement.objects.create(
        tenant_id=item.tenant_id,
        inventory_item=item,
        product_id=item.product_id,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=item.quantity,
        actor=actor,
        reference_type=reference_type[:32],
        reference_id=str(reference_id)[:64],
        note=note[:255],
    )


@transaction.atomic
def adjust_stock(
    *,
    product: Product,
    quantity_delta: Decimal | str | int,
    movement_type: str = MovementType.ADJUSTMENT,
    actor: User | None = None,
    note: str = "",
    reference_type: str = "",
    reference_id: str = "",
    allow_negative: bool | None = None,
) -> InventoryItem:
    """Change a stock level by ``quantity_delta`` and record the movement.

    Args:
        quantity_delta: Signed amount. Positive receives stock, negative removes it.
        allow_negative: Overrides the tenant's backorder setting. Cancellations
            and returns pass ``True`` because they can only increase stock.

    Raises:
        NegativeStockError: The result would be negative and backorders are off.
    """
    delta = quantize_quantity(quantity_delta)
    item = (
        InventoryItem.objects.select_for_update()
        .select_related("tenant", "product")
        .filter(product=product)
        .first()
    )
    if item is None:
        item = get_or_create_item(product)
        item = InventoryItem.objects.select_for_update().get(pk=item.pk)

    # Captured before the write, because "came back into stock" is a *transition*
    # and the only place both sides of it exist is here.
    was_available = item.available_quantity > 0

    new_quantity = item.quantity + delta
    permitted = allow_negative if allow_negative is not None else _allows_backorder(item.tenant)
    if new_quantity < 0 and not permitted:
        raise NegativeStockError(
            details={
                "product_id": str(product.pk),
                "current": str(item.quantity),
                "requested": str(delta),
            }
        )

    item.quantity = new_quantity
    item.save(update_fields=["quantity", "updated_at"])

    if not was_available and item.available_quantity > 0:
        _announce_restock(product)

    _write_movement(
        item=item,
        movement_type=movement_type,
        quantity=delta,
        actor=actor,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )

    record_audit(
        action="inventory.adjusted",
        tenant=item.tenant,
        actor=actor,
        resource=product,
        old_values={"quantity": str(new_quantity - delta)},
        new_values={"quantity": str(new_quantity), "type": movement_type},
    )
    logger.info(
        "stock_adjusted",
        extra={
            "event": "inventory.adjusted",
            "product_id": str(product.pk),
            "delta": str(delta),
            "balance": str(new_quantity),
        },
    )
    return item


@transaction.atomic
def set_stock(
    *, product: Product, quantity: Decimal | str, actor: User | None = None, note: str = ""
) -> InventoryItem:
    """Set an absolute quantity, recording the difference as an adjustment.

    A stock count produces an absolute number; the ledger still gets the delta
    so the history stays continuous.
    """
    target = quantize_quantity(quantity)
    item = get_or_create_item(product)
    item = InventoryItem.objects.select_for_update().get(pk=item.pk)
    return adjust_stock(
        product=product,
        quantity_delta=target - item.quantity,
        movement_type=MovementType.ADJUSTMENT,
        actor=actor,
        note=note or "Stock count",
        allow_negative=True,
    )


def check_availability(product: Product, quantity: Decimal | str | int) -> bool:
    """Whether ``quantity`` can be taken right now. Advisory only.

    The authoritative check happens inside :func:`reserve_stock`'s lock; this is
    for showing "out of stock" in a listing.
    """
    requested = quantize_quantity(quantity)
    item = InventoryItem.objects.filter(product=product).select_related("tenant").first()
    if item is None or not item.track_stock:
        return True
    if _allows_backorder(item.tenant):
        return True
    return item.available_quantity >= requested


@transaction.atomic
def reserve_stock(
    *,
    product: Product,
    quantity: Decimal | str | int,
    order: Order | None = None,
    ttl_seconds: int | None = None,
) -> StockReservation:
    """Hold ``quantity`` for a pending order.

    Raises:
        InsufficientStockError: Not enough available stock at the moment the
            lock was acquired.
    """
    requested = quantize_quantity(quantity)
    if requested <= 0:
        raise InsufficientStockError(_("The quantity must be greater than zero."))

    item = get_or_create_item(product)
    item = (
        InventoryItem.objects.select_for_update()
        .select_related("tenant", "product")
        .get(pk=item.pk)
    )

    if (
        item.track_stock
        and not _allows_backorder(item.tenant)
        and item.available_quantity < requested
    ):
        raise InsufficientStockError(
            details={
                "product_id": str(product.pk),
                "product_name": product.name,
                "requested": str(requested),
                "available": str(item.available_quantity),
            }
        )

    item.reserved_quantity += requested
    item.save(update_fields=["reserved_quantity", "updated_at"])

    reservation = StockReservation.objects.create(
        tenant_id=item.tenant_id,
        inventory_item=item,
        product=product,
        order=order,
        quantity=requested,
        expires_at=timezone.now()
        + timedelta(seconds=ttl_seconds or settings.STOCK_RESERVATION_TTL_SECONDS),
    )
    _write_movement(
        item=item,
        movement_type=MovementType.RESERVATION,
        quantity=Decimal("0.000"),  # physical stock is unchanged by a hold
        reference_type="reservation",
        reference_id=str(reservation.pk),
        note=f"Reserved {requested}",
    )
    return reservation


@transaction.atomic
def release_reservation(
    reservation: StockReservation, *, status: str = ReservationStatus.RELEASED
) -> StockReservation:
    """Return held stock to the available pool. Idempotent."""
    locked = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status != ReservationStatus.HELD:
        return locked

    item = InventoryItem.objects.select_for_update().get(pk=locked.inventory_item_id)
    item.reserved_quantity = max(item.reserved_quantity - locked.quantity, Decimal("0.000"))
    item.save(update_fields=["reserved_quantity", "updated_at"])

    locked.status = status
    locked.resolved_at = timezone.now()
    locked.save(update_fields=["status", "resolved_at", "updated_at"])

    _write_movement(
        item=item,
        movement_type=MovementType.RELEASE,
        quantity=Decimal("0.000"),
        reference_type="reservation",
        reference_id=str(locked.pk),
        note=f"Released {locked.quantity}",
    )
    return locked


@transaction.atomic
def commit_reservation(
    reservation: StockReservation, *, actor: User | None = None
) -> StockReservation:
    """Turn a hold into a sale: physical stock drops, the hold disappears.

    Idempotent, because payment webhooks can and do arrive twice
    (invariant #5).
    """
    locked = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status == ReservationStatus.COMMITTED:
        return locked
    if locked.status != ReservationStatus.HELD:
        raise ConflictError(
            _("This reservation is no longer active."),
            code="RESERVATION_NOT_HELD",
            details={"status": locked.status},
        )

    item = InventoryItem.objects.select_for_update().get(pk=locked.inventory_item_id)
    item.reserved_quantity = max(item.reserved_quantity - locked.quantity, Decimal("0.000"))
    item.quantity -= locked.quantity
    item.save(update_fields=["quantity", "reserved_quantity", "updated_at"])

    locked.status = ReservationStatus.COMMITTED
    locked.resolved_at = timezone.now()
    locked.save(update_fields=["status", "resolved_at", "updated_at"])

    _write_movement(
        item=item,
        movement_type=MovementType.SALE,
        quantity=-locked.quantity,
        actor=actor,
        reference_type="order",
        reference_id=str(locked.order_id or ""),
        note="Sale committed",
    )
    return locked


@transaction.atomic
def release_order_reservations(order: Order, *, status: str = ReservationStatus.RELEASED) -> int:
    """Release every hold attached to an order (cancellation, expiry)."""
    reservations = StockReservation.objects.filter(order=order, status=ReservationStatus.HELD)
    return sum(1 for reservation in reservations if release_reservation(reservation, status=status))


@transaction.atomic
def commit_order_reservations(order: Order, *, actor: User | None = None) -> int:
    """Commit every hold attached to an order once it is paid."""
    reservations = StockReservation.objects.filter(order=order, status=ReservationStatus.HELD)
    return sum(1 for reservation in reservations if commit_reservation(reservation, actor=actor))


@transaction.atomic
def restock_order(order: Order, *, actor: User | None = None) -> int:
    """Put items back after a refund or a return of an already-committed order."""
    restored = 0
    for reservation in StockReservation.objects.filter(
        order=order, status=ReservationStatus.COMMITTED
    ):
        adjust_stock(
            product=reservation.product,
            quantity_delta=reservation.quantity,
            movement_type=MovementType.RETURN,
            actor=actor,
            reference_type="order",
            reference_id=str(order.pk),
            note="Order returned",
            allow_negative=True,
        )
        restored += 1
    return restored


def expire_stale_reservations(limit: int = 500) -> int:
    """Release holds whose window has closed.

    Runs on a schedule. Without it, an abandoned checkout would keep stock
    unavailable indefinitely.
    """
    stale = StockReservation.objects.filter(
        status=ReservationStatus.HELD, expires_at__lte=timezone.now()
    ).order_by("expires_at")[:limit]

    released = 0
    for reservation in list(stale):
        release_reservation(reservation, status=ReservationStatus.EXPIRED)
        released += 1

    if released:
        logger.info("reservations_expired", extra={"event": "inventory.expired", "count": released})
    return released


def low_stock_items(tenant_id: Any, *, limit: int = 50) -> list[InventoryItem]:
    """Items at or below their reorder threshold, scarcest first."""
    from django.db.models import F

    return list(
        InventoryItem.objects.filter(tenant_id=tenant_id, track_stock=True)
        .filter(quantity__lte=F("reorder_threshold") + F("reserved_quantity"))
        .select_related("product")
        .order_by("quantity")[:limit]
    )


# =============================================================================
# Restock alerts
# =============================================================================
def _announce_restock(product: Product) -> None:
    """Queue the "it's back" emails, once the stock write has committed.

    Hooked into ``adjust_stock`` rather than into each caller because that is
    the single choke point every stock change passes through — a purchase
    received, a stock count, a cancelled order putting units back. A hook per
    caller would be a hook someone forgets.

    Deliberately *not* hooked into reservation release. Availability rises there
    too, but only because a checkout was abandoned; emailing forty people that a
    product is back because one cart timed out — when the next visitor takes the
    unit thirty seconds later — teaches them the alert means nothing.
    """
    if not RestockAlert.objects.filter(product=product, notified_at__isnull=True).exists():
        return

    from .tasks import notify_restocked

    transaction.on_commit(lambda: notify_restocked.delay(str(product.pk)))


def subscribe_to_restock(
    *,
    product: Product,
    customer: User | None = None,
    email: str = "",
    locale: str = "",
) -> RestockAlert | None:
    """Register interest in a product coming back.

    Returns ``None`` when there is nobody to notify. Re-subscribing after an
    earlier notification clears the stamp rather than creating a second row, so
    a shopper who asks twice is emailed once per restock, not twice.
    """
    address = (email or "").strip().lower()
    if customer is None and not address:
        return None

    lookup: dict[str, Any] = {"tenant": product.tenant, "product": product}
    if customer is not None:
        lookup["customer"] = customer
    else:
        lookup["customer"] = None
        lookup["email"] = address

    alert, created = RestockAlert.objects.get_or_create(
        **lookup,
        defaults={"email": address, "locale": locale or ""},
    )

    if not created:
        alert.notified_at = None
        alert.locale = locale or alert.locale
        if address and not alert.customer_id:
            alert.email = address
        alert.save(update_fields=["notified_at", "locale", "email", "updated_at"])

    return alert


def unsubscribe_from_restock(
    *, product: Product, customer: User | None = None, email: str = ""
) -> int:
    """Withdraw interest. Returns how many rows went."""
    queryset = RestockAlert.objects.filter(tenant=product.tenant, product=product)
    if customer is not None:
        queryset = queryset.filter(customer=customer)
    else:
        address = (email or "").strip().lower()
        if not address:
            return 0
        queryset = queryset.filter(customer__isnull=True, email=address)

    deleted, _detail = queryset.delete()
    return deleted


def restock_demand(tenant_id: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """Which unavailable products people are actually waiting for.

    The merchandising value of the whole feature: a ranked list of what to buy
    next, built from demand that never became an order and therefore appears in
    no sales report.
    """
    from django.db.models import Count, Max

    rows = (
        RestockAlert.objects.filter(tenant_id=tenant_id, notified_at__isnull=True)
        .values("product_id", "product__name", "product__sku", "product__slug")
        .annotate(waiting=Count("id"), since=Max("created_at"))
        .order_by("-waiting", "product__name")[:limit]
    )
    return [
        {
            "product_id": str(row["product_id"]),
            "name": row["product__name"],
            "sku": row["product__sku"],
            "slug": row["product__slug"],
            "waiting": row["waiting"],
            "latest_request": row["since"].isoformat() if row["since"] else None,
        }
        for row in rows
    ]
