"""
The payment provider contract.

Any PSP integration implements this interface. Two rules apply to every
implementation:

* :meth:`PaymentProvider.validate_webhook` must actually verify a signature.
  Returning ``True`` unconditionally turns the webhook endpoint into "anyone on
  the internet can mark orders as paid".
* :meth:`PaymentProvider.create_payment` must be safe to call twice with the
  same order — network timeouts happen, and a retry must not create a second
  charge.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from apps.orders.models import Order


@dataclass(frozen=True)
class PaymentResult:
    """What a provider returns after opening a charge."""

    external_id: str
    status: str
    amount: Decimal
    expires_at: datetime | None = None
    pix_payload: str = ""
    pix_qr_code: str = ""
    pix_transaction_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    external_id: str
    status: str
    amount: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookEvent:
    """A normalised provider callback.

    Providers disagree about payload shape; everything downstream works with
    this structure instead.
    """

    event_id: str
    event_type: str
    payment_external_id: str
    status: str
    amount: Decimal | None = None
    paid_at: datetime | None = None
    fee_amount: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    """Interface every PSP integration implements."""

    #: Registry key, also stored on each ``Payment`` row.
    name: str = "base"

    #: Methods this provider can collect.
    supported_methods: tuple[str, ...] = ()

    @abstractmethod
    def create_payment(
        self, *, order: Order, amount: Decimal, method: str, idempotency_key: str
    ) -> PaymentResult:
        """Open a charge for ``order``.

        ``idempotency_key`` is forwarded to the PSP so a retry returns the
        existing charge rather than creating a second one.
        """

    @abstractmethod
    def get_payment(self, external_id: str) -> PaymentResult:
        """Fetch the current state of a charge.

        Used to reconcile when a webhook is lost — never trust "the customer
        said they paid".
        """

    @abstractmethod
    def cancel_payment(self, external_id: str) -> PaymentResult:
        """Cancel an open charge."""

    @abstractmethod
    def refund_payment(
        self, *, external_id: str, amount: Decimal, reason: str = "", idempotency_key: str = ""
    ) -> RefundResult:
        """Refund part or all of a captured charge."""

    @abstractmethod
    def validate_webhook(self, *, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Verify the callback really came from the provider."""

    @abstractmethod
    def parse_webhook(self, *, raw_body: bytes, headers: dict[str, str]) -> WebhookEvent | None:
        """Normalise a callback, or return ``None`` for events we ignore."""

    def health_check(self) -> bool:
        """Whether the provider is reachable. Used by the readiness probe."""
        return True
