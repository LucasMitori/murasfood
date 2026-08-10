"""
The order state machine.

Invariant #7: a cancelled order cannot quietly become completed. Every legal
move is declared in ``apps.orders.constants.ALLOWED_TRANSITIONS`` and nothing
else may move an order.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.common.exceptions import ConflictError, InvalidStateTransitionError
from apps.orders.constants import OrderStatus, can_transition, next_statuses
from apps.orders.models import OrderStatusHistory
from apps.orders.services import cancel_order, register_refund, transition_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(tenant: Any, customer: Any, filled_cart: Any) -> Any:
    from apps.orders.services import create_order_from_cart

    return create_order_from_cart(
        tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
    )


class TestTransitionTable:
    def test_terminal_states_have_no_exit(self) -> None:
        assert next_statuses(OrderStatus.CANCELLED) == ()
        assert next_statuses(OrderStatus.REFUNDED) == ()

    def test_cancelled_cannot_become_completed(self) -> None:
        assert can_transition(OrderStatus.CANCELLED, OrderStatus.COMPLETED) is False

    def test_pending_payment_can_become_paid(self) -> None:
        assert can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.PAID) is True

    def test_pending_payment_cannot_skip_to_delivered(self) -> None:
        assert can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.DELIVERED) is False


class TestTransitions:
    def test_order_starts_awaiting_payment(self, order: Any) -> None:
        assert order.status == OrderStatus.PENDING_PAYMENT
        assert order.placed_at is not None

    def test_illegal_transition_is_rejected(self, order: Any) -> None:
        with pytest.raises(InvalidStateTransitionError):
            transition_order(order, to_status=OrderStatus.DELIVERED)

    def test_every_transition_is_recorded(self, order: Any, admin_user: Any) -> None:
        transition_order(order, to_status=OrderStatus.PAID, actor=admin_user, reason="Teste")

        entry = OrderStatusHistory.objects.filter(order=order).latest("created_at")
        assert entry.old_status == OrderStatus.PENDING_PAYMENT
        assert entry.new_status == OrderStatus.PAID
        assert entry.actor_id == admin_user.pk

    def test_history_is_immutable(self, order: Any) -> None:
        entry = OrderStatusHistory.objects.filter(order=order).first()
        entry.new_status = OrderStatus.COMPLETED

        with pytest.raises(ValueError, match="immutable"):
            entry.save()

    def test_repeating_the_current_status_is_a_no_op(self, order: Any) -> None:
        """Webhook replays must not create duplicate history or side effects."""
        before = OrderStatusHistory.objects.filter(order=order).count()
        transition_order(order, to_status=OrderStatus.PENDING_PAYMENT)

        assert OrderStatusHistory.objects.filter(order=order).count() == before

    def test_paying_commits_the_stock_reservation(self, order: Any, product: Any) -> None:
        from apps.inventory.models import InventoryItem

        transition_order(order, to_status=OrderStatus.PAID)

        item = InventoryItem.objects.get(product=product)
        assert item.quantity == Decimal("28.000")  # 30 − 2 sold
        assert item.reserved_quantity == Decimal("0.000")


class TestCancellation:
    def test_cancelling_releases_held_stock(self, order: Any, product: Any) -> None:
        from apps.inventory.models import InventoryItem

        assert InventoryItem.objects.get(product=product).reserved_quantity == Decimal("2.000")

        cancel_order(order, reason="Desistência")

        item = InventoryItem.objects.get(product=product)
        assert item.reserved_quantity == Decimal("0.000")
        assert item.quantity == Decimal("30.000")

    def test_cancelling_after_payment_restocks(self, order: Any, product: Any) -> None:
        from apps.inventory.models import InventoryItem

        transition_order(order, to_status=OrderStatus.PAID)
        assert InventoryItem.objects.get(product=product).quantity == Decimal("28.000")

        cancel_order(order, reason="Produto em falta")
        assert InventoryItem.objects.get(product=product).quantity == Decimal("30.000")

    def test_customer_cannot_cancel_a_paid_order(self, order: Any, customer: Any) -> None:
        transition_order(order, to_status=OrderStatus.PAID)

        with pytest.raises(ConflictError):
            cancel_order(order, actor=customer, by_customer=True)

    def test_customer_can_cancel_before_paying(self, order: Any, customer: Any) -> None:
        cancelled = cancel_order(order, actor=customer, by_customer=True, reason="Mudei de ideia")
        assert cancelled.status == OrderStatus.CANCELLED
        assert cancelled.cancellation_reason == "Mudei de ideia"


class TestRefunds:
    def _deliver(self, order: Any) -> Any:
        for target in (
            OrderStatus.PAID,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.COMPLETED,
        ):
            order.refresh_from_db()
            if order.status != target:
                order = transition_order(order, to_status=target)
        return order

    def test_refund_cannot_exceed_the_total(self, order: Any) -> None:
        """Invariant #8."""
        completed = self._deliver(order)

        with pytest.raises(ConflictError):
            register_refund(completed, amount=completed.total + Decimal("1.00"))

    def test_partial_refund_marks_the_order_partially_refunded(self, order: Any) -> None:
        completed = self._deliver(order)
        refunded = register_refund(completed, amount=Decimal("1.00"), reason="Item faltando")

        assert refunded.status == OrderStatus.PARTIALLY_REFUNDED
        assert refunded.refunded_total == Decimal("1.00")

    def test_full_refund_marks_the_order_refunded(self, order: Any) -> None:
        completed = self._deliver(order)
        refunded = register_refund(completed, amount=completed.total)

        assert refunded.status == OrderStatus.REFUNDED
        assert refunded.net_total == Decimal("0.00")

    def test_refunds_accumulate_up_to_the_total(self, order: Any) -> None:
        completed = self._deliver(order)
        register_refund(completed, amount=Decimal("5.00"))
        completed.refresh_from_db()
        register_refund(completed, amount=Decimal("5.00"))
        completed.refresh_from_db()

        assert completed.refunded_total == Decimal("10.00")
