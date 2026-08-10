"""
Order lifecycle.

The transition table below is the whole state machine. Nothing else in the
codebase may move an order between states — that is what stops a cancelled
order from quietly becoming completed (invariant #7).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PENDING_PAYMENT = "PENDING_PAYMENT", _("Awaiting payment")
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING", _("Processing payment")
    PAID = "PAID", _("Paid")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    PREPARING = "PREPARING", _("Being prepared")
    READY_FOR_PICKUP = "READY_FOR_PICKUP", _("Ready for pickup")
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", _("Out for delivery")
    DELIVERED = "DELIVERED", _("Delivered")
    COMPLETED = "COMPLETED", _("Completed")
    CANCELLED = "CANCELLED", _("Cancelled")
    PAYMENT_FAILED = "PAYMENT_FAILED", _("Payment failed")
    REFUNDED = "REFUNDED", _("Refunded")
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", _("Partially refunded")


#: ``current -> allowed next``. An empty tuple marks a terminal state.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    OrderStatus.DRAFT: (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED),
    OrderStatus.PENDING_PAYMENT: (
        OrderStatus.PAYMENT_PROCESSING,
        OrderStatus.PAID,
        OrderStatus.PAYMENT_FAILED,
        OrderStatus.CANCELLED,
    ),
    OrderStatus.PAYMENT_PROCESSING: (
        OrderStatus.PAID,
        OrderStatus.PAYMENT_FAILED,
        OrderStatus.CANCELLED,
    ),
    OrderStatus.PAID: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED, OrderStatus.REFUNDED),
    OrderStatus.CONFIRMED: (
        OrderStatus.PREPARING,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ),
    OrderStatus.PREPARING: (
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ),
    OrderStatus.READY_FOR_PICKUP: (
        OrderStatus.COMPLETED,
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ),
    OrderStatus.OUT_FOR_DELIVERY: (
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ),
    OrderStatus.DELIVERED: (
        OrderStatus.COMPLETED,
        OrderStatus.REFUNDED,
        OrderStatus.PARTIALLY_REFUNDED,
    ),
    OrderStatus.COMPLETED: (OrderStatus.REFUNDED, OrderStatus.PARTIALLY_REFUNDED),
    # Terminal.
    OrderStatus.CANCELLED: (),
    OrderStatus.PAYMENT_FAILED: (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED),
    OrderStatus.REFUNDED: (),
    OrderStatus.PARTIALLY_REFUNDED: (OrderStatus.REFUNDED,),
}

#: States in which stock is still held rather than sold.
STOCK_HELD_STATUSES = frozenset(
    {OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING}
)

#: States a customer may cancel from without staff involvement.
CUSTOMER_CANCELLABLE_STATUSES = frozenset(
    {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_FAILED, OrderStatus.DRAFT}
)

#: States that count as revenue in financial reports. Cancelled and failed
#: orders never do — spec §29 is explicit that revenue is not "orders created".
REVENUE_STATUSES = frozenset(
    {
        OrderStatus.PAID,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
        OrderStatus.COMPLETED,
        OrderStatus.PARTIALLY_REFUNDED,
    }
)

#: Open orders needing merchant attention, for the dashboard counter.
ACTIVE_STATUSES = frozenset(
    {
        OrderStatus.PAID,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.OUT_FOR_DELIVERY,
    }
)


def can_transition(current: str, target: str) -> bool:
    """Whether ``current -> target`` is a legal move."""
    return target in ALLOWED_TRANSITIONS.get(current, ())


def next_statuses(current: str) -> tuple[str, ...]:
    """Legal next states, for rendering the merchant's action buttons."""
    return ALLOWED_TRANSITIONS.get(current, ())


#: Customer-facing timeline steps, in display order (spec §94).
TIMELINE_STEPS: tuple[tuple[str, str], ...] = (
    (OrderStatus.PENDING_PAYMENT, "order.timeline.pending_payment"),
    (OrderStatus.PAID, "order.timeline.paid"),
    (OrderStatus.CONFIRMED, "order.timeline.confirmed"),
    (OrderStatus.PREPARING, "order.timeline.preparing"),
    (OrderStatus.READY_FOR_PICKUP, "order.timeline.ready"),
    (OrderStatus.OUT_FOR_DELIVERY, "order.timeline.out_for_delivery"),
    (OrderStatus.DELIVERED, "order.timeline.delivered"),
    (OrderStatus.COMPLETED, "order.timeline.completed"),
)
