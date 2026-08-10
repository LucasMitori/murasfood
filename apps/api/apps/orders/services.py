"""
Order services: checkout and the state machine.

Checkout is the most safety-critical path in the platform. The order of
operations matters and is deliberate:

1. validate the cart (products purchasable, prices resolvable),
2. re-price every line **server-side** — the client's numbers are ignored,
3. recompute discounts server-side,
4. quote delivery server-side,
5. reserve stock under row locks,
6. write the order with immutable snapshots,
7. leave it in ``PENDING_PAYMENT``.

Only a validated payment provider callback can move it to ``PAID``
(invariant #4).
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import record_audit
from apps.common.exceptions import ConflictError, DomainError, InvalidStateTransitionError
from apps.common.money import money_multiply, quantize_money

from .constants import (
    ALLOWED_TRANSITIONS,
    STOCK_HELD_STATUSES,
    OrderStatus,
    can_transition,
)
from .models import Order, OrderAddress, OrderItem, OrderStatusHistory

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import Address, User
    from apps.cart.models import Cart
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.orders")

ZERO = Decimal("0.00")
_NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters


class EmptyCartError(DomainError):
    default_detail = _("Your cart is empty.")
    default_code = "CART_EMPTY"


class CheckoutValidationError(DomainError):
    default_detail = _("Some items in your cart are unavailable.")
    default_code = "CHECKOUT_VALIDATION_FAILED"


class StoreClosedError(DomainError):
    default_detail = _("The store is closed and is not accepting orders right now.")
    default_code = "STORE_CLOSED"


def generate_order_number(tenant: Tenant) -> str:
    """Human-friendly, tenant-scoped order number: ``MF-240815-K7P2QX``.

    Random rather than sequential on purpose: a sequential number leaks how many
    orders a merchant takes, and a global counter is a contention point under
    concurrent checkout.
    """
    settings_row = getattr(tenant, "settings", None)
    prefix = (settings_row.order_number_prefix if settings_row else "MF") or "MF"
    stamp = timezone.now().strftime("%y%m%d")
    suffix = "".join(secrets.choice(_NUMBER_ALPHABET) for _ in range(6))
    return f"{prefix}-{stamp}-{suffix}"


def _record_transition(
    order: Order,
    *,
    old_status: str,
    new_status: str,
    actor: User | None = None,
    reason: str = "",
    customer_visible: bool = True,
) -> OrderStatusHistory:
    return OrderStatusHistory.objects.create(
        tenant_id=order.tenant_id,
        order=order,
        old_status=old_status,
        new_status=new_status,
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=str(actor) if getattr(actor, "pk", None) else "system",
        reason=reason[:255],
        is_customer_visible=customer_visible,
    )


# =============================================================================
# Checkout
# =============================================================================
@transaction.atomic
def create_order_from_cart(
    *,
    tenant: Tenant,
    cart: Cart,
    delivery_method: str,
    address: Address | None = None,
    customer: User | None = None,
    customer_note: str = "",
    scheduled_for: Any = None,
    contact: dict[str, str] | None = None,
) -> Order:
    """Turn a cart into a ``PENDING_PAYMENT`` order.

    Raises:
        EmptyCartError: Nothing to check out.
        CheckoutValidationError: A line is unavailable or unpriced.
        InsufficientStockError: Stock ran out between the cart view and now.
        DeliveryUnavailableError / MinimumOrderNotMetError: Delivery rules.
        StoreClosedError: Outside business hours with scheduling disabled.
    """
    from apps.cart.selectors import cart_discount_result, unavailable_items
    from apps.cart.services import mark_converted
    from apps.delivery.models import DeliveryMethod
    from apps.delivery.selectors import quote_delivery
    from apps.inventory.services import reserve_stock
    from apps.pricing.selectors import resolve_price
    from apps.promotions.services import redeem_coupon
    from apps.tenants.selectors import is_open_at

    if cart.is_empty:
        raise EmptyCartError()

    problems = unavailable_items(cart)
    if problems:
        raise CheckoutValidationError(details={"items": problems})

    settings_row = getattr(tenant, "settings", None)
    if not is_open_at(tenant) and not (settings_row and settings_row.allow_orders_when_closed):
        raise StoreClosedError()

    if delivery_method == DeliveryMethod.DELIVERY and address is None:
        raise CheckoutValidationError(_("Select a delivery address."), code="ADDRESS_REQUIRED")

    # --- 2. Re-price every line from the pricing engine ----------------------
    priced_lines: list[dict[str, Any]] = []
    subtotal = ZERO
    for item in cart.items.select_related("product", "product__category", "product__sale_unit"):
        resolved = resolve_price(item.product, quantity=item.quantity)
        if resolved is None:
            raise CheckoutValidationError(
                details={"product": item.product.name, "reason": "NO_PRICE"}
            )
        line_total = money_multiply(resolved.unit_price, item.quantity)
        subtotal += line_total
        priced_lines.append(
            {
                "product": item.product,
                "quantity": item.quantity,
                "unit_price": resolved.unit_price,
                "base_unit_price": resolved.base_price,
                "unit_cost": resolved.cost_price,
                "line_total": line_total,
                "note": item.note,
            }
        )
    subtotal = quantize_money(subtotal)

    # --- 3. Discounts, recomputed regardless of what the cart showed ---------
    discounts = cart_discount_result(cart, coupon_code=cart.coupon_code)

    # --- 4. Delivery, quoted server-side -------------------------------------
    quote = quote_delivery(
        tenant=tenant,
        method=delivery_method,
        subtotal=subtotal - discounts.total_discount,
        postal_code=address.postal_code if address else "",
    )
    delivery_fee = ZERO if discounts.free_delivery else quote.fee

    order = _persist_order(
        tenant=tenant,
        customer=customer,
        contact=contact or {},
        delivery_method=delivery_method,
        subtotal=subtotal,
        discount_total=discounts.total_discount,
        delivery_fee=delivery_fee,
        coupon_code=discounts.coupon.code if discounts.coupon else "",
        customer_note=customer_note,
        scheduled_for=scheduled_for,
        estimated_minutes=quote.estimated_minutes,
    )

    for line in priced_lines:
        product = line["product"]
        OrderItem.objects.create(
            tenant_id=tenant.pk,
            order=order,
            product=product,
            product_name=product.name,
            product_sku=product.sku,
            unit_code=product.sale_unit.code if product.sale_unit_id else "",
            category_name=product.category.name if product.category_id else "",
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            base_unit_price=line["base_unit_price"],
            unit_cost=line["unit_cost"],
            line_total=line["line_total"],
            note=line["note"],
        )

    if address is not None:
        OrderAddress.objects.create(tenant_id=tenant.pk, order=order, **address.as_snapshot())

    # --- 5. Reserve stock (row-locked; may still raise) ----------------------
    for line in priced_lines:
        reserve_stock(product=line["product"], quantity=line["quantity"], order=order)

    if discounts.coupon is not None:
        redeem_coupon(
            coupon=discounts.coupon, order=order, discount_amount=discounts.total_discount
        )

    _record_transition(
        order,
        old_status=OrderStatus.DRAFT,
        new_status=OrderStatus.PENDING_PAYMENT,
        actor=customer,
        reason="Checkout",
    )
    mark_converted(cart)

    record_audit(
        action="order.created",
        tenant=tenant,
        actor=customer,
        resource=order,
        new_values={"number": order.number, "total": str(order.total)},
    )
    logger.info(
        "order_created",
        extra={
            "event": "orders.created",
            "order_id": str(order.pk),
            "number": order.number,
            "total": str(order.total),
        },
    )
    return order


def _persist_order(
    *,
    tenant: Tenant,
    customer: User | None,
    contact: dict[str, str],
    delivery_method: str,
    subtotal: Decimal,
    discount_total: Decimal,
    delivery_fee: Decimal,
    coupon_code: str,
    customer_note: str,
    scheduled_for: Any,
    estimated_minutes: int,
) -> Order:
    """Create the order row, retrying if a generated number collides."""
    for attempt in range(5):
        order = Order(
            tenant=tenant,
            number=generate_order_number(tenant),
            customer=customer,
            customer_name=contact.get("name") or (customer.get_full_name() if customer else ""),
            customer_email=contact.get("email") or (customer.email if customer else ""),
            customer_phone=contact.get("phone") or (customer.phone if customer else ""),
            status=OrderStatus.PENDING_PAYMENT,
            delivery_method=delivery_method,
            currency=tenant.currency,
            subtotal=subtotal,
            discount_total=discount_total,
            delivery_fee=delivery_fee,
            coupon_code=coupon_code,
            customer_note=customer_note[:500],
            scheduled_for=scheduled_for,
            placed_at=timezone.now(),
            estimated_ready_at=timezone.now() + timedelta(minutes=estimated_minutes),
        )
        order.recalculate_total()
        try:
            with transaction.atomic():
                order.save()
            return order
        except IntegrityError:
            if attempt == 4:
                raise
            continue
    raise ConflictError(_("Could not allocate an order number."), code="ORDER_NUMBER_COLLISION")


# =============================================================================
# State machine
# =============================================================================
@transaction.atomic
def transition_order(
    order: Order,
    *,
    to_status: str,
    actor: User | None = None,
    reason: str = "",
    customer_visible: bool = True,
) -> Order:
    """Move an order to ``to_status``, enforcing the transition table.

    Side effects that belong to a transition — committing stock, releasing
    reservations, stamping timestamps, notifying the customer — happen here, so
    they cannot be forgotten by a caller.

    Raises:
        InvalidStateTransitionError: The move is not allowed from the current
            state.
    """
    locked = Order.objects.select_for_update().get(pk=order.pk)
    current = locked.status

    if current == to_status:
        # Idempotent: a webhook replay must not fail or duplicate side effects.
        return locked

    if not can_transition(current, to_status):
        raise InvalidStateTransitionError(
            details={
                "from": current,
                "to": to_status,
                "allowed": list(ALLOWED_TRANSITIONS.get(current, ())),
            }
        )

    _apply_transition_effects(locked, current=current, target=to_status, actor=actor)

    locked.status = to_status
    locked.save()

    _record_transition(
        locked,
        old_status=current,
        new_status=to_status,
        actor=actor,
        reason=reason,
        customer_visible=customer_visible,
    )
    record_audit(
        action="order.status_changed",
        tenant=locked.tenant,
        actor=actor,
        resource=locked,
        old_values={"status": current},
        new_values={"status": to_status, "reason": reason},
    )

    _notify_status_change(locked, previous=current)

    logger.info(
        "order_status_changed",
        extra={
            "event": "orders.status_changed",
            "order_id": str(locked.pk),
            "from": current,
            "to": to_status,
        },
    )
    return locked


def _apply_transition_effects(
    order: Order, *, current: str, target: str, actor: User | None
) -> None:
    """Run the inventory and timestamp side effects for one transition."""
    from apps.inventory.services import (
        commit_order_reservations,
        release_order_reservations,
        restock_order,
    )

    now = timezone.now()

    if target == OrderStatus.PAID:
        # Held stock becomes sold stock exactly once, when money is confirmed.
        commit_order_reservations(order, actor=actor)
        order.paid_at = order.paid_at or now

    elif target in (OrderStatus.CANCELLED, OrderStatus.PAYMENT_FAILED):
        if current in STOCK_HELD_STATUSES:
            release_order_reservations(order)
        else:
            # Already committed: put the goods back on the shelf.
            restock_order(order, actor=actor)
        if target == OrderStatus.CANCELLED:
            order.cancelled_at = now
            from apps.promotions.services import revert_redemptions

            revert_redemptions(order)

    elif target == OrderStatus.REFUNDED:
        restock_order(order, actor=actor)
        order.refunded_total = order.total

    elif target in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
        order.completed_at = order.completed_at or now
        _increment_sales_counters(order)


def _increment_sales_counters(order: Order) -> None:
    """Bump the denormalised ``sales_count`` used for merchandising."""
    from django.db.models import F

    from apps.catalog.models import Product

    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                sales_count=F("sales_count") + int(item.quantity)
            )


def _notify_status_change(order: Order, *, previous: str) -> None:
    """Queue the customer notification for this transition, if any."""
    from apps.notifications.services import notify_order_status

    try:
        notify_order_status(order, previous_status=previous)
    except Exception:
        logger.exception("order_notification_failed", extra={"event": "orders.notification_failed"})


def mark_order_paid(order: Order, *, actor: User | None = None, reason: str = "") -> Order:
    """Confirm payment and auto-advance when the tenant wants that.

    Called only from the payment layer after a provider callback has been
    verified.
    """
    paid = transition_order(
        order, to_status=OrderStatus.PAID, actor=actor, reason=reason or "Payment confirmed"
    )

    settings_row = getattr(paid.tenant, "settings", None)
    if settings_row and settings_row.auto_confirm_paid_orders:
        paid = transition_order(
            paid, to_status=OrderStatus.CONFIRMED, actor=actor, reason="Auto-confirmed"
        )
    return paid


def cancel_order(
    order: Order, *, actor: User | None = None, reason: str = "", by_customer: bool = False
) -> Order:
    """Cancel an order, restoring stock and coupon uses.

    Customers may only cancel while the order is still unpaid; anything later
    needs staff, because it may involve a refund.
    """
    # Re-read before deciding: the caller may be holding an instance loaded
    # before a payment webhook landed, and "was unpaid a moment ago" is not a
    # licence to cancel a paid order.
    order.refresh_from_db()

    if by_customer and not order.is_cancellable_by_customer:
        raise ConflictError(
            _("This order can no longer be cancelled. Please contact the store."),
            code="ORDER_NOT_CANCELLABLE",
            details={"status": order.status},
        )

    cancelled = transition_order(
        order, to_status=OrderStatus.CANCELLED, actor=actor, reason=reason or "Cancelled"
    )
    cancelled.cancellation_reason = reason[:255]
    cancelled.save(update_fields=["cancellation_reason", "updated_at"])
    return cancelled


@transaction.atomic
def register_refund(
    order: Order, *, amount: Decimal, actor: User | None = None, reason: str = ""
) -> Order:
    """Record a refund against an order.

    Refunds can never exceed what was captured (invariant #8), and a partial
    refund keeps the order in a distinct state so reports can tell the two
    apart.
    """
    locked = Order.objects.select_for_update().get(pk=order.pk)
    amount = quantize_money(amount)

    if amount <= 0:
        raise DomainError(_("The refund amount must be positive."), code="INVALID_REFUND_AMOUNT")

    remaining = locked.total - locked.refunded_total
    if amount > remaining:
        raise ConflictError(
            _("The refund exceeds the amount available."),
            code="REFUND_EXCEEDS_TOTAL",
            details={"available": str(remaining), "requested": str(amount)},
        )

    locked.refunded_total = quantize_money(locked.refunded_total + amount)
    locked.save(update_fields=["refunded_total", "updated_at"])

    target = (
        OrderStatus.REFUNDED
        if locked.refunded_total >= locked.total
        else OrderStatus.PARTIALLY_REFUNDED
    )
    if can_transition(locked.status, target):
        locked = transition_order(
            locked, to_status=target, actor=actor, reason=reason or "Refund issued"
        )

    record_audit(
        action="payment.refunded",
        tenant=locked.tenant,
        actor=actor,
        resource=locked,
        new_values={"amount": str(amount), "refunded_total": str(locked.refunded_total)},
    )
    return locked


def add_note(
    *, order: Order, author: User | None, body: str, customer_visible: bool = False
) -> Any:
    from .models import OrderNote

    return OrderNote.objects.create(
        tenant_id=order.tenant_id,
        order=order,
        author=author,
        body=body,
        is_customer_visible=customer_visible,
    )


def expire_unpaid_orders(*, older_than_minutes: int = 60, limit: int = 200) -> int:
    """Cancel orders that were never paid, freeing their reserved stock."""
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    stale = Order.objects.filter(
        status=OrderStatus.PENDING_PAYMENT, created_at__lt=cutoff
    ).order_by("created_at")[:limit]

    cancelled = 0
    for order in list(stale):
        try:
            cancel_order(order, reason="Payment window expired")
            cancelled += 1
        except DomainError:
            logger.warning(
                "order_expiry_failed",
                extra={"event": "orders.expiry_failed", "order_id": str(order.pk)},
            )
    return cancelled
