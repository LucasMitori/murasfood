"""
Sandbox PIX provider.

A deterministic, offline implementation used for development and the automated
test suite. It produces a *real, valid* BR Code — so the QR a developer scans
actually parses — but it never talks to a bank and never moves money.

Confirmation happens through the same webhook path a real PSP would use, signed
with ``PAYMENT_WEBHOOK_SECRET``, so the production code path is the one under
test. ``config.settings.production`` warns loudly if this provider is still
configured.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.utils import timezone

from ..constants import PaymentMethod, PaymentStatus
from .base import PaymentProvider, PaymentResult, RefundResult, WebhookEvent
from .pix import build_br_code, render_qr_code_base64, sanitize_txid

if TYPE_CHECKING:  # pragma: no cover
    from apps.orders.models import Order

logger = logging.getLogger("murasfood.payments")

SIGNATURE_HEADER = "X-Murasfood-Signature"

#: Obviously fake key: no real PIX account can receive from this sandbox.
SANDBOX_PIX_KEY = "sandbox@murasfood.invalid"


class SandboxPixProvider(PaymentProvider):
    """Offline PIX provider."""

    name = "sandbox"
    supported_methods = (PaymentMethod.PIX, PaymentMethod.CASH)

    # --- Charges -------------------------------------------------------------
    def create_payment(
        self, *, order: Order, amount: Decimal, method: str, idempotency_key: str
    ) -> PaymentResult:
        """Open a simulated PIX charge with a valid BR Code."""
        txid = sanitize_txid(order.number.replace("-", ""))
        external_id = f"sbx_{secrets.token_hex(12)}"
        expires_at = timezone.now() + timedelta(seconds=settings.PAYMENT_PIX_EXPIRATION_SECONDS)

        tenant = order.tenant
        payload = build_br_code(
            pix_key=SANDBOX_PIX_KEY,
            merchant_name=tenant.trade_name,
            merchant_city=tenant.city or "SAO PAULO",
            amount=amount,
            txid=txid,
            description=f"Pedido {order.number}",
        )

        logger.info(
            "sandbox_payment_created",
            extra={
                "event": "payments.sandbox.created",
                "order_number": order.number,
                "amount": str(amount),
            },
        )
        return PaymentResult(
            external_id=external_id,
            status=PaymentStatus.PENDING,
            amount=amount,
            expires_at=expires_at,
            pix_payload=payload,
            pix_qr_code=render_qr_code_base64(payload),
            pix_transaction_id=txid,
            metadata={"sandbox": True, "idempotency_key": idempotency_key},
        )

    def get_payment(self, external_id: str) -> PaymentResult:
        """Report the charge as still pending.

        The sandbox has no bank to ask; confirmation arrives through the webhook
        simulation endpoint instead.
        """
        return PaymentResult(
            external_id=external_id,
            status=PaymentStatus.PENDING,
            amount=Decimal("0.00"),
            metadata={"sandbox": True},
        )

    def cancel_payment(self, external_id: str) -> PaymentResult:
        return PaymentResult(
            external_id=external_id,
            status=PaymentStatus.CANCELLED,
            amount=Decimal("0.00"),
            metadata={"sandbox": True},
        )

    def refund_payment(
        self, *, external_id: str, amount: Decimal, reason: str = "", idempotency_key: str = ""
    ) -> RefundResult:
        logger.info(
            "sandbox_refund",
            extra={"event": "payments.sandbox.refund", "amount": str(amount)},
        )
        return RefundResult(
            external_id=f"sbxref_{secrets.token_hex(8)}",
            status="COMPLETED",
            amount=amount,
            metadata={"sandbox": True, "reason": reason},
        )

    # --- Webhooks ------------------------------------------------------------
    @staticmethod
    def sign(raw_body: bytes) -> str:
        """HMAC-SHA256 of the raw body, hex encoded."""
        secret = (settings.PAYMENT_WEBHOOK_SECRET or "").encode("utf-8")
        return hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    def validate_webhook(self, *, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Verify the HMAC signature in constant time.

        An unsigned deployment is refused outright rather than defaulting to
        "accept everything" — the failure mode of a permissive webhook endpoint
        is fraudulent free orders.
        """
        if not settings.PAYMENT_WEBHOOK_SECRET:
            logger.error(
                "webhook_secret_not_configured",
                extra={"event": "payments.webhook.no_secret"},
            )
            return False

        provided = headers.get(SIGNATURE_HEADER) or headers.get(SIGNATURE_HEADER.lower()) or ""
        return hmac.compare_digest(provided, self.sign(raw_body))

    def parse_webhook(self, *, raw_body: bytes, headers: dict[str, str]) -> WebhookEvent | None:
        """Normalise the sandbox payload.

        Expected body::

            {
              "id": "evt_123",
              "type": "payment.paid",
              "payment_id": "sbx_...",
              "status": "PAID",
              "amount": "42.90",
              "fee": "0.40"
            }
        """
        try:
            data: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            logger.warning("webhook_unparseable", extra={"event": "payments.webhook.bad_body"})
            return None

        payment_id = data.get("payment_id") or data.get("external_id")
        if not payment_id:
            return None

        status = str(data.get("status") or "").upper()
        if status not in PaymentStatus.values:
            return None

        amount = data.get("amount")
        fee = data.get("fee")

        return WebhookEvent(
            event_id=str(data.get("id") or f"evt_{secrets.token_hex(8)}"),
            event_type=str(data.get("type") or "payment.updated"),
            payment_external_id=str(payment_id),
            status=status,
            amount=Decimal(str(amount)) if amount is not None else None,
            fee_amount=Decimal(str(fee)) if fee is not None else None,
            paid_at=timezone.now() if status == PaymentStatus.PAID else None,
            raw=data,
        )
