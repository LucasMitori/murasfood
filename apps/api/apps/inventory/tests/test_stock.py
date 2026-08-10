"""
Inventory correctness.

The scenarios that matter: stock must not go negative, reservations must hold
stock without consuming it, and two customers must not both buy the last unit
(spec §50, invariant #6).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.common.exceptions import InsufficientStockError
from apps.inventory.models import InventoryItem, MovementType, ReservationStatus, StockMovement
from apps.inventory.services import (
    adjust_stock,
    check_availability,
    commit_reservation,
    expire_stale_reservations,
    low_stock_items,
    release_reservation,
    reserve_stock,
    set_stock,
)

pytestmark = pytest.mark.django_db


def item_for(product: Any) -> InventoryItem:
    return InventoryItem.objects.get(product=product)


class TestAdjustments:
    def test_every_change_writes_a_movement(self, product: Any) -> None:
        """Stock is never silently overwritten (spec §12)."""
        before = StockMovement.objects.filter(product=product).count()
        adjust_stock(product=product, quantity_delta="5", movement_type=MovementType.PURCHASE)

        assert StockMovement.objects.filter(product=product).count() == before + 1
        movement = StockMovement.objects.filter(product=product).latest("created_at")
        assert movement.quantity == Decimal("5.000")
        assert movement.balance_after == item_for(product).quantity

    def test_movements_are_immutable(self, product: Any) -> None:
        adjust_stock(product=product, quantity_delta="1")
        movement = StockMovement.objects.filter(product=product).latest("created_at")

        movement.quantity = Decimal("999")
        with pytest.raises(ValueError, match="immutable"):
            movement.save()

    def test_stock_cannot_go_negative(self, product: Any) -> None:
        from apps.inventory.services import NegativeStockError

        with pytest.raises(NegativeStockError):
            adjust_stock(product=product, quantity_delta="-1000")

        assert item_for(product).quantity == Decimal("30.000")

    def test_backorder_setting_allows_negative(self, tenant: Any, product: Any) -> None:
        tenant.settings.allow_backorder = True
        tenant.settings.save()

        adjust_stock(product=product, quantity_delta="-100")
        assert item_for(product).quantity < 0

    def test_stock_count_records_the_difference(self, product: Any) -> None:
        set_stock(product=product, quantity="12", note="Contagem")

        item = item_for(product)
        assert item.quantity == Decimal("12.000")
        movement = StockMovement.objects.filter(product=product).latest("created_at")
        assert movement.quantity == Decimal("-18.000")


class TestReservations:
    def test_reservation_holds_without_consuming(self, product: Any) -> None:
        reserve_stock(product=product, quantity="4")

        item = item_for(product)
        assert item.quantity == Decimal("30.000")  # physical stock unchanged
        assert item.reserved_quantity == Decimal("4.000")
        assert item.available_quantity == Decimal("26.000")

    def test_cannot_reserve_more_than_available(self, product: Any) -> None:
        with pytest.raises(InsufficientStockError):
            reserve_stock(product=product, quantity="31")

    def test_last_unit_cannot_be_reserved_twice(self, product_factory: Any) -> None:
        """The core oversell scenario from spec §50."""
        single = product_factory(name="Último item", stock="1")

        reserve_stock(product=single, quantity="1")
        with pytest.raises(InsufficientStockError):
            reserve_stock(product=single, quantity="1")

    def test_release_returns_stock_to_the_pool(self, product: Any) -> None:
        reservation = reserve_stock(product=product, quantity="5")
        release_reservation(reservation)

        item = item_for(product)
        assert item.reserved_quantity == Decimal("0.000")
        assert item.available_quantity == Decimal("30.000")

    def test_release_is_idempotent(self, product: Any) -> None:
        reservation = reserve_stock(product=product, quantity="3")
        release_reservation(reservation)
        release_reservation(reservation)

        assert item_for(product).reserved_quantity == Decimal("0.000")

    def test_commit_turns_a_hold_into_a_sale(self, product: Any) -> None:
        reservation = reserve_stock(product=product, quantity="6")
        commit_reservation(reservation)

        item = item_for(product)
        assert item.quantity == Decimal("24.000")
        assert item.reserved_quantity == Decimal("0.000")

        movement = StockMovement.objects.filter(
            product=product, movement_type=MovementType.SALE
        ).latest("created_at")
        assert movement.quantity == Decimal("-6.000")

    def test_commit_is_idempotent(self, product: Any) -> None:
        """A payment webhook arriving twice must not deduct stock twice."""
        reservation = reserve_stock(product=product, quantity="6")
        commit_reservation(reservation)
        commit_reservation(reservation)

        assert item_for(product).quantity == Decimal("24.000")

    def test_expired_reservations_are_released(self, product: Any) -> None:
        reservation = reserve_stock(product=product, quantity="7")
        reservation.expires_at = timezone.now() - timedelta(minutes=1)
        reservation.save(update_fields=["expires_at"])

        assert expire_stale_reservations() == 1

        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.EXPIRED
        assert item_for(product).available_quantity == Decimal("30.000")


class TestAvailability:
    def test_untracked_products_are_always_available(self, product: Any) -> None:
        """Fresh bakery batches are made to order, not counted."""
        item = item_for(product)
        item.track_stock = False
        item.save()

        assert check_availability(product, "1000") is True

    def test_low_stock_listing(self, product_factory: Any) -> None:
        scarce = product_factory(name="Quase acabando", stock="2")
        item = item_for(scarce)
        item.reorder_threshold = Decimal("5.000")
        item.save()

        assert scarce.pk in {row.product_id for row in low_stock_items(scarce.tenant_id)}
