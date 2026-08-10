"""Payment enumerations and the payment state machine."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", _("Awaiting payment")
    PROCESSING = "PROCESSING", _("Processing")
    PAID = "PAID", _("Paid")
    FAILED = "FAILED", _("Failed")
    EXPIRED = "EXPIRED", _("Expired")
    CANCELLED = "CANCELLED", _("Cancelled")
    REFUNDED = "REFUNDED", _("Refunded")
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", _("Partially refunded")


class PaymentMethod(models.TextChoices):
    PIX = "PIX", _("PIX")
    CREDIT_CARD = "CREDIT_CARD", _("Credit card")
    DEBIT_CARD = "DEBIT_CARD", _("Debit card")
    CASH = "CASH", _("Cash on delivery")
    WALLET = "WALLET", _("Digital wallet")


class RefundStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")


class WebhookProcessingStatus(models.TextChoices):
    RECEIVED = "RECEIVED", _("Received")
    PROCESSED = "PROCESSED", _("Processed")
    IGNORED = "IGNORED", _("Ignored")
    FAILED = "FAILED", _("Failed")


#: Legal payment state moves. A payment that already reached a terminal state
#: cannot be re-opened by a late or replayed webhook.
ALLOWED_PAYMENT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    PaymentStatus.PENDING: (
        PaymentStatus.PROCESSING,
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
        PaymentStatus.EXPIRED,
        PaymentStatus.CANCELLED,
    ),
    PaymentStatus.PROCESSING: (
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
        PaymentStatus.EXPIRED,
        PaymentStatus.CANCELLED,
    ),
    PaymentStatus.PAID: (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED),
    PaymentStatus.PARTIALLY_REFUNDED: (PaymentStatus.REFUNDED,),
    PaymentStatus.FAILED: (PaymentStatus.PENDING,),
    PaymentStatus.EXPIRED: (PaymentStatus.PENDING,),
    PaymentStatus.CANCELLED: (),
    PaymentStatus.REFUNDED: (),
}

#: Statuses that still expect customer action.
OPEN_PAYMENT_STATUSES = frozenset({PaymentStatus.PENDING, PaymentStatus.PROCESSING})


def can_transition_payment(current: str, target: str) -> bool:
    return target in ALLOWED_PAYMENT_TRANSITIONS.get(current, ())
