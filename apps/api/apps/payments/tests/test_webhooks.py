"""
Payment webhooks.

Invariants under test:

* #4 — only a *verified* provider callback can mark a payment as paid,
* #5 — a replayed webhook is a no-op.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.payments.constants import PaymentStatus
from apps.payments.models import Payment, PaymentEvent
from apps.payments.providers.sandbox import SIGNATURE_HEADER, SandboxPixProvider
from apps.payments.services import WebhookSignatureError, create_payment_for_order, process_webhook

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/payments/webhooks/"


@pytest.fixture
def order(tenant: Any, customer: Any, filled_cart: Any) -> Any:
    from apps.orders.services import create_order_from_cart

    return create_order_from_cart(
        tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
    )


@pytest.fixture
def payment(order: Any) -> Payment:
    return create_payment_for_order(order=order)


def webhook_body(
    payment: Payment, *, event_id: str = "evt_1", status: str = "PAID", **extra: Any
) -> bytes:
    body = {
        "id": event_id,
        "type": "payment.paid",
        "payment_id": payment.external_id,
        "status": status,
        "amount": str(payment.amount),
        **extra,
    }
    return json.dumps(body).encode("utf-8")


def signed(body: bytes) -> dict[str, str]:
    return {SIGNATURE_HEADER: SandboxPixProvider.sign(body)}


class TestPaymentCreation:
    def test_payment_carries_a_valid_pix_code(self, payment: Payment) -> None:
        from apps.payments.providers.pix import verify_br_code

        assert payment.status == PaymentStatus.PENDING
        assert verify_br_code(payment.pix_payload) is True
        assert payment.expires_at is not None

    def test_reopening_returns_the_existing_charge(self, order: Any, payment: Payment) -> None:
        """A customer refreshing the payment page must not get a second code."""
        again = create_payment_for_order(order=order)
        assert again.pk == payment.pk
        assert Payment.objects.filter(order=order).count() == 1


class TestSignatureVerification:
    def test_unsigned_callback_is_rejected(self, payment: Payment) -> None:
        with pytest.raises(WebhookSignatureError):
            process_webhook(raw_body=webhook_body(payment), headers={}, provider_name="sandbox")

    def test_wrong_signature_is_rejected(self, payment: Payment) -> None:
        with pytest.raises(WebhookSignatureError):
            process_webhook(
                raw_body=webhook_body(payment),
                headers={SIGNATURE_HEADER: "deadbeef"},
                provider_name="sandbox",
            )

    def test_unsigned_request_over_http_returns_401(
        self, api_client: APIClient, payment: Payment
    ) -> None:
        response = api_client.post(
            WEBHOOK_URL, data=webhook_body(payment), content_type="application/json"
        )
        assert response.status_code == 401

    def test_missing_secret_refuses_everything(self, settings: Any, payment: Payment) -> None:
        """A deployment without a webhook secret must fail closed."""
        settings.PAYMENT_WEBHOOK_SECRET = ""
        body = webhook_body(payment)

        with pytest.raises(WebhookSignatureError):
            process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")


class TestProcessing:
    def test_valid_callback_marks_the_payment_and_order_paid(
        self, payment: Payment, order: Any
    ) -> None:
        body = webhook_body(payment)
        result = process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")

        assert result["status"] == "processed"

        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == PaymentStatus.PAID
        assert payment.paid_at is not None
        assert order.status in ("PAID", "CONFIRMED")
        assert order.paid_at is not None

    def test_paying_commits_the_stock(self, payment: Payment, product: Any) -> None:
        from apps.inventory.models import InventoryItem

        body = webhook_body(payment)
        process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")

        item = InventoryItem.objects.get(product=product)
        assert item.quantity == Decimal("28.000")
        assert item.reserved_quantity == Decimal("0.000")

    def test_replayed_event_is_ignored(self, payment: Payment, product: Any) -> None:
        """Invariant #5: the provider retrying must not deduct stock twice."""
        from apps.inventory.models import InventoryItem

        body = webhook_body(payment, event_id="evt_replay")
        first = process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")
        second = process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")

        assert first["status"] == "processed"
        assert second["status"] == "duplicate"
        assert InventoryItem.objects.get(product=product).quantity == Decimal("28.000")
        assert PaymentEvent.objects.filter(provider_event_id="evt_replay").count() == 1

    def test_amount_mismatch_is_refused(self, payment: Payment, order: Any) -> None:
        """A provider reporting a different amount must not confirm the order."""
        body = webhook_body(payment, event_id="evt_mismatch", amount="0.01")
        result = process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")

        assert result["status"] == "rejected"
        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING
        assert order.paid_at is None

    def test_unknown_payment_reference_is_recorded_and_ignored(self, tenant: Any) -> None:
        body = json.dumps(
            {
                "id": "evt_unknown",
                "type": "payment.paid",
                "payment_id": "sbx_does_not_exist",
                "status": "PAID",
            }
        ).encode("utf-8")

        result = process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")
        assert result["status"] == "ignored"
        assert PaymentEvent.objects.filter(provider_event_id="evt_unknown").exists()

    def test_failed_payment_marks_the_order_failed(self, payment: Payment, order: Any) -> None:
        body = webhook_body(payment, event_id="evt_failed", status="FAILED")
        process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")

        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert order.status == "PAYMENT_FAILED"

    def test_paid_payment_cannot_go_back_to_pending(self, payment: Payment) -> None:
        paid_body = webhook_body(payment, event_id="evt_paid")
        process_webhook(raw_body=paid_body, headers=signed(paid_body), provider_name="sandbox")

        late_body = webhook_body(payment, event_id="evt_late", status="PENDING")
        process_webhook(raw_body=late_body, headers=signed(late_body), provider_name="sandbox")

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PAID


class TestRefunds:
    def test_refund_cannot_exceed_the_captured_amount(self, payment: Payment) -> None:
        from apps.payments.services import PaymentNotRefundableError, refund_payment

        body = webhook_body(payment)
        process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")
        payment.refresh_from_db()

        with pytest.raises(PaymentNotRefundableError):
            refund_payment(payment=payment, amount=payment.amount + Decimal("1.00"))

    def test_unpaid_payment_cannot_be_refunded(self, payment: Payment) -> None:
        from apps.payments.services import PaymentNotRefundableError, refund_payment

        with pytest.raises(PaymentNotRefundableError):
            refund_payment(payment=payment, amount=Decimal("1.00"))

    def test_partial_refund_updates_the_balance(self, payment: Payment) -> None:
        from apps.payments.services import refund_payment

        body = webhook_body(payment)
        process_webhook(raw_body=body, headers=signed(body), provider_name="sandbox")
        payment.refresh_from_db()

        refund_payment(payment=payment, amount=Decimal("5.00"), reason="Item faltando")
        payment.refresh_from_db()

        assert payment.refunded_amount == Decimal("5.00")
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
        assert payment.refundable_amount == payment.amount - Decimal("5.00")
