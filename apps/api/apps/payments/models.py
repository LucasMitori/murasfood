"""
Payment models.

Deliberately *not* stored: card numbers, CVVs, or anything else that would put
this system in PCI scope (spec §19). What is stored is the minimum needed to
reconcile a charge with a bank statement: provider, external id, amount, status
and timestamps.

``PaymentEvent`` is the webhook ledger. Every callback is recorded before it is
acted upon, with a unique constraint on the provider's event id — that is what
makes replayed webhooks harmless (invariant #5).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel

from .constants import (
    OPEN_PAYMENT_STATUSES,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    WebhookProcessingStatus,
)


class Payment(TenantOwnedModel):
    """One attempt to collect money for an order."""

    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="payments", verbose_name=_("order")
    )

    provider = models.CharField(_("provider"), max_length=32)
    external_id = models.CharField(
        _("provider reference"),
        max_length=128,
        blank=True,
        db_index=True,
        help_text=_("The provider's identifier, used for reconciliation."),
    )

    method = models.CharField(
        _("method"), max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.PIX
    )
    status = models.CharField(
        _("status"), max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    refunded_amount = models.DecimalField(
        _("refunded"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    fee_amount = models.DecimalField(
        _("provider fee"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Charged by the PSP. Subtracted from revenue in financial reports."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="BRL")

    # --- PIX -----------------------------------------------------------------
    pix_payload = models.TextField(
        _("PIX copy-and-paste code"),
        blank=True,
        help_text=_("The BR Code string the customer pastes into their bank app."),
    )
    pix_qr_code = models.TextField(
        _("PIX QR code"), blank=True, help_text=_("Base64 PNG rendering of the BR Code.")
    )
    pix_transaction_id = models.CharField(_("PIX txid"), max_length=64, blank=True)

    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    failure_reason = models.CharField(_("failure reason"), max_length=255, blank=True)

    metadata = models.JSONField(_("provider metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(refunded_amount__lte=models.F("amount")),
                name="payment_refund_within_amount",
            ),
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_payment_provider_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["order", "-created_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.provider}:{self.external_id or self.pk} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_PAYMENT_STATUSES

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now() and self.is_open)

    @property
    def refundable_amount(self) -> Decimal:
        """What may still be refunded (invariant #8)."""
        if self.status not in {PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED}:
            return Decimal("0.00")
        return self.amount - self.refunded_amount

    @property
    def net_amount(self) -> Decimal:
        """Amount actually received: paid, less refunds and the provider fee."""
        return self.amount - self.refunded_amount - self.fee_amount


class PaymentEvent(TenantOwnedModel):
    """A webhook callback, recorded before it is processed.

    The unique ``(payment, provider_event_id)`` constraint is the idempotency
    guarantee: a provider retrying a callback cannot confirm the same payment
    twice.
    """

    # A callback can arrive for a reference we do not recognise — a charge from
    # another environment, or one created before a restore. It still has to be
    # recorded for investigation, so both the payment and the tenant are
    # nullable here even though tenant is mandatory everywhere else.
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="payment_events",
        null=True,
        blank=True,
        verbose_name=_("tenant"),
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
        verbose_name=_("payment"),
    )
    provider = models.CharField(_("provider"), max_length=32)
    provider_event_id = models.CharField(_("event id"), max_length=128, db_index=True)
    event_type = models.CharField(_("event type"), max_length=64)

    payload_hash = models.CharField(
        _("payload hash"),
        max_length=64,
        help_text=_("SHA-256 of the raw body — enough to detect duplicates and tampering."),
    )
    payload = models.JSONField(_("payload"), default=dict, blank=True)

    signature_valid = models.BooleanField(_("signature valid"), default=False)
    processing_status = models.CharField(
        _("processing status"),
        max_length=12,
        choices=WebhookProcessingStatus.choices,
        default=WebhookProcessingStatus.RECEIVED,
    )
    processing_error = models.CharField(_("processing error"), max_length=255, blank=True)
    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("payment event")
        verbose_name_plural = _("payment events")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                condition=~models.Q(provider_event_id=""),
                name="uniq_payment_event_provider_id",
            ),
        ]
        indexes = [
            models.Index(fields=["payment", "-created_at"]),
            models.Index(fields=["processing_status", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.provider}:{self.event_type}"


class PaymentRefund(TenantOwnedModel):
    """A refund issued against a payment."""

    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="refunds", verbose_name=_("payment")
    )
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    status = models.CharField(
        _("status"), max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING
    )
    external_id = models.CharField(_("provider reference"), max_length=128, blank=True)
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="refund_amount_positive"),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"Refund {self.amount} on {self.payment_id}"
