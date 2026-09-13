"""
Shelf life.

The questions a shop asks every morning: what has already gone off, what turns
this week, and what it is worth if it goes in the bin. The boundaries are what
matter here — a batch expiring *today* is still sellable, one that expired
yesterday is not, and a spent batch is history rather than a warning.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.inventory.models import StockBatch

pytestmark = pytest.mark.django_db


def make_batch(
    product: Any, *, days: int, quantity: str = "10", cost: str | None = "2.00"
) -> StockBatch:
    """A batch expiring `days` from today; negative means it already has."""
    today = timezone.localdate()
    return StockBatch.objects.create(
        tenant=product.tenant,
        product=product,
        quantity=Decimal(quantity),
        expiry_date=today + timedelta(days=days),
        # Received far enough back that it never post-dates the expiry.
        received_date=today - timedelta(days=30),
        cost_price=None if cost is None else Decimal(cost),
    )


class TestExpiryBoundaries:
    def test_expiring_today_is_not_yet_expired(self, product: Any) -> None:
        """A date is a deadline, not a fence: it is sellable until it passes."""
        batch = make_batch(product, days=0)

        assert batch.is_expired is False
        assert batch.days_remaining == 0
        assert batch not in StockBatch.objects.expired()

    def test_expired_yesterday_is_expired(self, product: Any) -> None:
        batch = make_batch(product, days=-1)

        assert batch.is_expired is True
        assert batch.days_remaining == -1
        assert batch in StockBatch.objects.expired()

    def test_expiring_within_excludes_what_already_expired(self, product: Any) -> None:
        """Pulling stock off a shelf and discounting stock are different jobs.

        Folding the expired into the "expiring soon" list buries the urgent work
        under the routine.
        """
        gone = make_batch(product, days=-2)
        soon = make_batch(product, days=3)

        window = list(StockBatch.objects.expiring_within(7))

        assert soon in window
        assert gone not in window

    def test_window_is_inclusive_of_its_last_day(self, product: Any) -> None:
        edge = make_batch(product, days=7)
        beyond = make_batch(product, days=8)

        window = list(StockBatch.objects.expiring_within(7))

        assert edge in window
        assert beyond not in window


class TestRemaining:
    def test_a_spent_batch_is_not_a_warning(self, product: Any) -> None:
        """Nothing is left to pull off the shelf, so it should not be listed."""
        spent = make_batch(product, days=-5, quantity="0")

        assert spent not in StockBatch.objects.expired()
        assert spent not in StockBatch.objects.expiring_within(30)


class TestWriteOffValue:
    def test_value_is_cost_times_quantity(self, product: Any) -> None:
        batch = make_batch(product, days=2, quantity="4", cost="3.50")

        assert batch.write_off_value == Decimal("14.00")

    def test_unknown_cost_is_none_rather_than_zero(self, product: Any) -> None:
        """Zero would quietly understate a write-off; unknown says so."""
        batch = make_batch(product, days=2, cost=None)

        assert batch.write_off_value is None


class TestOrdering:
    def test_soonest_to_expire_comes_first(self, product: Any) -> None:
        """The order the shelf should be worked in."""
        late = make_batch(product, days=30)
        early = make_batch(product, days=1)
        middle = make_batch(product, days=10)

        assert list(StockBatch.objects.all()) == [early, middle, late]


class TestApi:
    def test_expiry_report_separates_gone_from_going(self, admin_client: Any, product: Any) -> None:
        make_batch(product, days=-1, quantity="2", cost="5.00")
        make_batch(product, days=3, quantity="4", cost="5.00")

        response = admin_client.get("/api/v1/admin/inventory/expiry/?days=7")

        assert response.status_code == 200
        body = response.json()
        assert body["expired_count"] == 1
        assert body["expiring_count"] == 1
        assert body["expired_value"] == "10.00"
        assert body["expiring_value"] == "20.00"

    def test_expiry_cannot_precede_receipt(self, admin_client: Any, product: Any) -> None:
        today = timezone.localdate()
        response = admin_client.post(
            "/api/v1/admin/stock-batches/",
            {
                "product": str(product.pk),
                "quantity": "5",
                "received_date": today.isoformat(),
                "expiry_date": (today - timedelta(days=1)).isoformat(),
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        # The API wraps field errors in its own envelope rather than returning
        # DRF's bare dict, so the message is asserted where callers find it.
        assert "expiry_date" in response.json()["error"]["details"]

    def test_malformed_window_is_rejected_not_ignored(
        self, admin_client: Any, product: Any
    ) -> None:
        """Answering with every batch ever received would look like success."""
        make_batch(product, days=3)

        response = admin_client.get("/api/v1/admin/stock-batches/?expiring_days=soon")

        assert response.status_code == 400


class TestStockHealth:
    """The four bands must partition the catalog: every product in exactly one.

    A product counted in two bands, or in none, makes the summary contradict
    the list beside it — which is the one thing a dashboard must never do.
    """

    def test_bands_sum_to_the_whole_catalog(self, admin_client: Any, product: Any) -> None:
        from apps.inventory.models import InventoryItem

        total = InventoryItem.objects.count()
        body = admin_client.get("/api/v1/admin/inventory/health/").json()

        assert body["out"] + body["low"] + body["healthy"] + body["untracked"] == total

    def test_out_of_stock_is_not_also_counted_as_low(self, admin_client: Any, product: Any) -> None:
        """Running down and already gone are different jobs, and different bands."""
        from apps.inventory.models import InventoryItem

        item = InventoryItem.objects.get(product=product)
        item.quantity = Decimal("0")
        item.reorder_threshold = Decimal("5")
        item.save(update_fields=["quantity", "reorder_threshold"])

        body = admin_client.get("/api/v1/admin/inventory/health/").json()
        listed_low = admin_client.get("/api/v1/admin/inventory/?stock_state=low").json()
        listed_out = admin_client.get("/api/v1/admin/inventory/?stock_state=out").json()

        low_ids = [row["product"] for row in listed_low["results"]]
        out_ids = [row["product"] for row in listed_out["results"]]

        assert str(product.pk) in out_ids
        assert str(product.pk) not in low_ids
        assert body["out"] >= 1

    def test_counts_agree_with_the_lists_they_summarise(
        self, admin_client: Any, product: Any
    ) -> None:
        body = admin_client.get("/api/v1/admin/inventory/health/").json()

        for state in ("out", "low", "healthy", "untracked"):
            listed = admin_client.get(f"/api/v1/admin/inventory/?stock_state={state}").json()
            assert listed["count"] == body[state], f"{state} count disagrees with its list"

    def test_unknown_state_is_rejected(self, admin_client: Any) -> None:
        response = admin_client.get("/api/v1/admin/inventory/?stock_state=banana")

        assert response.status_code == 400
