"""
Payment services.

The rule that governs this module: **only a verified provider callback can mark
a payment as paid** (invariant #4). Nothing here accepts a status from a client
request, and the webhook path verifies a signature before it reads the body.
"""

from __future__ import annotations

import hashlib
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import record_audit
from apps.common.exceptions import ConflictError, PaymentError
from apps.common.money import quantize_money

from .constants import (
    OPEN_PAYMENT_STATUSES,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    WebhookProcessingStatus,
    can_transition_payment,
)
from .models import Payment, PaymentEvent, PaymentRefund
from .providers import get_provider

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.orders.models import Order

logger = logging.getLogger("murasfood.payments")


class PaymentNotRefundableError(ConflictError):
    default_detail = _("This payment cannot be refunded.")
    default_code = "PAYMENT_NOT_REFUNDABLE"


class WebhookSignatureError(PaymentError):
    default_detail = _("Invalid webhook signature.")
    default_code = "INVALID_WEBHOOK_SIGNATURE"
    status_code = 401


# =============================================================================
# Creating charges
# =============================================================================
@transaction.atomic
def create_payment_for_order(
    *, order: Order, method: str = PaymentMethod.PIX, provider_name: str | None = None
) -> Payment:
    """Open a charge for an order.

    Reuses an existing open payment rather than creating a second one: a
    customer refreshing the payment page must not end up with two PIX codes for
    the same order.
    """
    existing = (
        Payment.objects.select_for_update()
        .filter(order=order, status__in=OPEN_PAYMENT_STATUSES)
        .order_by("-created_at")
        .first()
    )
    if existing is not None and not existing.is_expired:
        return existing

    provider = get_provider(provider_name)
    amount = quantize_money(order.total)
    if amount <= 0:
        raise PaymentError(_("The order total must be greater than zero."), code="INVALID_AMOUNT")

    result = provider.create_payment(
        order=order,
        amount=amount,
        method=method,
        idempotency_key=f"order-{order.pk}",
    )

    payment = Payment.objects.create(
        tenant_id=order.tenant_id,
        order=order,
        provider=provider.name,
        external_id=result.external_id,
        method=method,
        status=result.status or PaymentStatus.PENDING,
        amount=amount,
        currency=order.currency,
        pix_payload=result.pix_payload,
        pix_qr_code=result.pix_qr_code,
        pix_transaction_id=result.pix_transaction_id,
        expires_at=result.expires_at,
        metadata=result.metadata,
    )

    logger.info(
        "payment_created",
        extra={
            "event": "payments.created",
            "payment_id": str(payment.pk),
            "order_number": order.number,
            "provider": provider.name,
        },
    )
    return payment


# =============================================================================
# State changes
# =============================================================================
@transaction.atomic
def apply_payment_status(
    payment: Payment,
    *,
    status: str,
    paid_at: Any = None,
    fee_amount: Decimal | None = None,
    failure_reason: str = "",
    actor: User | None = None,
) -> Payment:
    """Move a payment to ``status`` and propagate the change to its order.

    Idempotent: repeating the current status is a no-op, which is what makes a
    replayed webhook harmless.
    """
    locked = (
        Payment.objects.select_for_update().select_related("order", "tenant").get(pk=payment.pk)
    )
    current = locked.status

    if current == status:
        return locked

    if not can_transition_payment(current, status):
        logger.warning(
            "payment_transition_rejected",
            extra={
                "event": "payments.transition_rejected",
                "payment_id": str(locked.pk),
                "from": current,
                "to": status,
            },
        )
        return locked

    locked.status = status
    if status == PaymentStatus.PAID:
        locked.paid_at = paid_at or timezone.now()
        if fee_amount is not None:
            locked.fee_amount = quantize_money(fee_amount)
    if failure_reason:
        locked.failure_reason = failure_reason[:255]
    locked.save()

    record_audit(
        action="payment.status_changed",
        tenant=locked.tenant,
        actor=actor,
        resource=locked,
        old_values={"status": current},
        new_values={"status": status},
    )

    _propagate_to_order(locked, status=status, actor=actor)
    return locked


def _propagate_to_order(payment: Payment, *, status: str, actor: User | None) -> None:
    """Mirror a payment outcome onto its order."""
    from apps.orders.constants import OrderStatus
    from apps.orders.services import mark_order_paid, transition_order

    order = payment.order

    if status == PaymentStatus.PAID:
        mark_order_paid(order, actor=actor, reason="Payment confirmed by the provider")
    elif status in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
        if order.status == OrderStatus.PENDING_PAYMENT:
            transition_order(
                order,
                to_status=OrderStatus.PAYMENT_FAILED,
                actor=actor,
                reason=f"Payment {status.lower()}",
            )
    elif status == PaymentStatus.PROCESSING and order.status == OrderStatus.PENDING_PAYMENT:
        transition_order(
            order,
            to_status=OrderStatus.PAYMENT_PROCESSING,
            actor=actor,
            reason="Payment being processed",
        )


# =============================================================================
# Webhooks
# =============================================================================
def process_webhook(
    *, raw_body: bytes, headers: dict[str, str], provider_name: str | None = None
) -> dict[str, Any]:
    """Verify, record and apply a provider callback.

    Order of operations is the point:

    1. verify the signature — an unverified body is never parsed as truth,
    2. record the event with a unique provider event id,
    3. bail out early if that id was already processed,
    4. only then change any payment or order state.

    Raises:
        WebhookSignatureError: The signature did not verify.
    """
    provider = get_provider(provider_name)

    if not provider.validate_webhook(raw_body=raw_body, headers=headers):
        logger.warning(
            "webhook_signature_invalid", extra={"event": "payments.webhook.invalid_signature"}
        )
        raise WebhookSignatureError()

    event = provider.parse_webhook(raw_body=raw_body, headers=headers)
    if event is None:
        return {"status": "ignored", "reason": "unrecognised_event"}

    payment = (
        Payment.objects.filter(provider=provider.name, external_id=event.payment_external_id)
        .select_related("order", "tenant")
        .first()
    )

    payload_hash = hashlib.sha256(raw_body).hexdigest()

    try:
        with transaction.atomic():
            record = PaymentEvent.objects.create(
                tenant_id=payment.tenant_id if payment else None,
                payment=payment,
                provider=provider.name,
                provider_event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=payload_hash,
                payload=event.raw,
                signature_valid=True,
            )
    except IntegrityError:
        # Already seen: the provider is retrying. Report success so it stops.
        logger.info(
            "webhook_duplicate_ignored",
            extra={"event": "payments.webhook.duplicate", "event_id": event.event_id},
        )
        return {"status": "duplicate", "event_id": event.event_id}

    if payment is None:
        record.processing_status = WebhookProcessingStatus.IGNORED
        record.processing_error = "Unknown payment reference"
        record.processed_at = timezone.now()
        record.save(update_fields=["processing_status", "processing_error", "processed_at"])
        logger.warning(
            "webhook_unknown_payment",
            extra={
                "event": "payments.webhook.unknown_payment",
                "external_id": event.payment_external_id,
            },
        )
        return {"status": "ignored", "reason": "unknown_payment"}

    # A provider reporting a different amount than we charged is a red flag:
    # record it and refuse to confirm rather than shipping goods for less.
    if event.amount is not None and quantize_money(event.amount) != quantize_money(payment.amount):
        record.processing_status = WebhookProcessingStatus.FAILED
        record.processing_error = "Amount mismatch"
        record.processed_at = timezone.now()
        record.save(update_fields=["processing_status", "processing_error", "processed_at"])
        logger.error(
            "webhook_amount_mismatch",
            extra={
                "event": "payments.webhook.amount_mismatch",
                "expected": str(payment.amount),
                "received": str(event.amount),
            },
        )
        return {"status": "rejected", "reason": "amount_mismatch"}

    try:
        apply_payment_status(
            payment,
            status=event.status,
            paid_at=event.paid_at,
            fee_amount=event.fee_amount,
        )
        record.processing_status = WebhookProcessingStatus.PROCESSED
    except Exception as exc:
        record.processing_status = WebhookProcessingStatus.FAILED
        record.processing_error = str(exc)[:255]
        record.processed_at = timezone.now()
        record.save(update_fields=["processing_status", "processing_error", "processed_at"])
        logger.exception("webhook_processing_failed", extra={"event": "payments.webhook.failed"})
        raise

    record.processed_at = timezone.now()
    record.save(update_fields=["processing_status", "processed_at"])

    logger.info(
        "webhook_processed",
        extra={
            "event": "payments.webhook.processed",
            "event_id": event.event_id,
            "payment_id": str(payment.pk),
            "status": event.status,
        },
    )
    return {"status": "processed", "payment_status": event.status}


# =============================================================================
# Refunds
# =============================================================================
@transaction.atomic
def refund_payment(
    *, payment: Payment, amount: Decimal, actor: User | None = None, reason: str = ""
) -> PaymentRefund:
    """Refund through the provider and record the result.

    Raises:
        PaymentNotRefundableError: The payment was never captured, or the amount
            exceeds what remains (invariant #8).
    """
    locked = Payment.objects.select_for_update().get(pk=payment.pk)
    amount = quantize_money(amount)

    if locked.status not in {PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED}:
        raise PaymentNotRefundableError(details={"status": locked.status})
    if amount <= 0 or amount > locked.refundable_amount:
        raise PaymentNotRefundableError(
            _("The refund exceeds the amount available."),
            code="REFUND_EXCEEDS_PAYMENT",
            details={"available": str(locked.refundable_amount), "requested": str(amount)},
        )

    provider = get_provider(locked.provider)
    result = provider.refund_payment(
        external_id=locked.external_id,
        amount=amount,
        reason=reason,
        idempotency_key=f"refund-{locked.pk}-{amount}",
    )

    refund = PaymentRefund.objects.create(
        tenant_id=locked.tenant_id,
        payment=locked,
        amount=amount,
        status=RefundStatus.COMPLETED if result.status == "COMPLETED" else RefundStatus.PENDING,
        external_id=result.external_id,
        reason=reason[:255],
        requested_by=actor,
        completed_at=timezone.now() if result.status == "COMPLETED" else None,
    )

    if refund.status == RefundStatus.COMPLETED:
        locked.refunded_amount = quantize_money(locked.refunded_amount + amount)
        locked.status = (
            PaymentStatus.REFUNDED
            if locked.refunded_amount >= locked.amount
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        locked.save(update_fields=["refunded_amount", "status", "updated_at"])

    record_audit(
        action="payment.refunded",
        tenant=locked.tenant,
        actor=actor,
        resource=locked,
        new_values={"amount": str(amount), "reason": reason},
    )
    return refund


def refund_order_payment(
    *, order: Order, amount: Decimal, actor: User | None = None, reason: str = ""
) -> PaymentRefund | None:
    """Refund the paid payment attached to an order."""
    payment = (
        Payment.objects.filter(
            order=order, status__in=[PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED]
        )
        .order_by("-created_at")
        .first()
    )
    if payment is None:
        return None
    return refund_payment(payment=payment, amount=amount, actor=actor, reason=reason)


# =============================================================================
# Reconciliation
# =============================================================================
def expire_open_payments(*, limit: int = 200) -> int:
    """Mark payments whose PIX window has closed as expired."""
    stale = Payment.objects.filter(
        status__in=OPEN_PAYMENT_STATUSES, expires_at__lte=timezone.now()
    ).order_by("expires_at")[:limit]

    expired = 0
    for payment in list(stale):
        apply_payment_status(payment, status=PaymentStatus.EXPIRED, failure_reason="Expired")
        expired += 1
    return expired


def reconcile_payment(payment: Payment) -> Payment:
    """Ask the provider for the truth about one payment.

    The safety net for a lost webhook. The provider's answer wins; ours never
    does.
    """
    provider = get_provider(payment.provider)
    try:
        result = provider.get_payment(payment.external_id)
    except Exception:
        logger.exception(
            "payment_reconciliation_failed", extra={"event": "payments.reconcile_failed"}
        )
        return payment

    if result.status and result.status != payment.status:
        return apply_payment_status(payment, status=result.status)
    return payment
