"""Pricing engine and price history."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.pricing.models import PriceHistory, ProductPrice
from apps.pricing.selectors import annotate_effective_price, margin_metrics, resolve_price
from apps.pricing.services import InvalidPriceError, set_price

pytestmark = pytest.mark.django_db


class TestPriceResolution:
    def test_base_price_is_used_without_a_promotion(self, tenant: Any, product: Any) -> None:
        resolved = resolve_price(product)
        assert resolved is not None
        assert resolved.unit_price == Decimal("12.50")
        assert resolved.is_discounted is False

    def test_sale_price_wins_when_present(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="12.50", sale_price="9.90")

        resolved = resolve_price(product)
        assert resolved is not None
        assert resolved.unit_price == Decimal("9.90")
        assert resolved.base_price == Decimal("12.50")
        assert resolved.is_discounted is True
        assert resolved.discount_amount == Decimal("2.60")

    def test_sale_price_above_base_is_rejected(self, tenant: Any, product: Any) -> None:
        with pytest.raises(InvalidPriceError):
            set_price(tenant=tenant, product=product, base_price="10.00", sale_price="15.00")

    def test_quantity_tier_applies_from_its_threshold(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="10.00", min_quantity=Decimal("6.000"))

        assert resolve_price(product, quantity=1).unit_price == Decimal("12.50")
        assert resolve_price(product, quantity=6).unit_price == Decimal("10.00")

    def test_scheduled_price_outside_its_window_is_ignored(
        self, tenant: Any, product_factory: Any
    ) -> None:
        future = product_factory(name="Promo futura", price="20.00")
        set_price(
            tenant=tenant,
            product=future,
            base_price="20.00",
            sale_price="12.00",
            starts_at=timezone.now() + timedelta(days=3),
            ends_at=timezone.now() + timedelta(days=6),
        )

        assert resolve_price(future) is None or resolve_price(future).unit_price == Decimal("20.00")

    def test_product_without_a_price_resolves_to_none(
        self, tenant: Any, category: Any, unit: Any
    ) -> None:
        from apps.catalog.services import create_product

        unpriced = create_product(
            tenant=tenant, name="Sem preço", category=category, sale_unit=unit
        )
        assert resolve_price(unpriced) is None


class TestPriceHistory:
    def test_initial_price_is_recorded(self, product: Any) -> None:
        entries = PriceHistory.objects.filter(product=product, field="base_price")
        assert entries.count() == 1
        assert entries.first().new_value == Decimal("12.50")

    def test_change_records_old_and_new(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="14.00")

        latest = PriceHistory.objects.filter(product=product, field="base_price").latest(
            "created_at"
        )
        assert latest.old_value == Decimal("12.50")
        assert latest.new_value == Decimal("14.00")
        assert latest.variation == Decimal("1.50")

    def test_history_cannot_be_rewritten(self, product: Any) -> None:
        """Invariant #10: historical prices are immutable."""
        entry = PriceHistory.objects.filter(product=product).first()
        entry.new_value = Decimal("1.00")

        with pytest.raises(ValueError, match="immutable"):
            entry.save()

    def test_unchanged_field_writes_no_history(self, tenant: Any, product: Any) -> None:
        before = PriceHistory.objects.filter(product=product).count()
        set_price(tenant=tenant, product=product, base_price="12.50", cost_price="8.00")

        assert PriceHistory.objects.filter(product=product).count() == before


class TestAnnotation:
    def test_effective_price_annotation_matches_resolution(self, product: Any) -> None:
        from apps.catalog.models import Product

        annotated = annotate_effective_price(Product.objects.filter(pk=product.pk)).first()
        assert annotated.effective_price == resolve_price(product).unit_price

    def test_annotation_prefers_the_sale_price(self, tenant: Any, product: Any) -> None:
        from apps.catalog.models import Product

        set_price(tenant=tenant, product=product, base_price="12.50", sale_price="8.00")
        annotated = annotate_effective_price(Product.objects.filter(pk=product.pk)).first()

        assert annotated.effective_price == Decimal("8.00")
        assert annotated.base_price == Decimal("12.50")

    def test_sorting_by_price_happens_in_sql(self, product_factory: Any) -> None:
        from apps.catalog.models import Product

        product_factory(name="Barato", price="3.00")
        product_factory(name="Caro", price="99.00")

        ordered = list(annotate_effective_price(Product.objects.all()).order_by("effective_price"))
        assert ordered[0].name == "Barato"
        assert ordered[-1].name == "Caro"


class TestMarginMetrics:
    def test_metrics_are_reported_together(self) -> None:
        metrics = margin_metrics(Decimal("20.00"), Decimal("12.00"))
        assert metrics["gross_margin"] == Decimal("8.00")
        assert metrics["gross_margin_percentage"] == Decimal("40.00")
        assert metrics["markup_percentage"] == Decimal("66.67")

    def test_unknown_cost_yields_nulls_not_zeros(self) -> None:
        """Reporting a zero margin for unknown cost would be a lie."""
        metrics = margin_metrics(Decimal("20.00"), None)
        assert metrics["gross_margin"] is None


def test_bulk_adjust_keeps_history(tenant: Any, product_factory: Any) -> None:
    from apps.pricing.services import bulk_adjust_prices

    first = product_factory(name="A", price="10.00")
    second = product_factory(name="B", price="20.00")

    changed = bulk_adjust_prices(tenant=tenant, products=[first, second], percentage=Decimal("10"))
    assert changed == 2

    assert resolve_price(first).unit_price == Decimal("11.00")
    assert resolve_price(second).unit_price == Decimal("22.00")
    assert PriceHistory.objects.filter(product=first, field="base_price").count() == 2


def test_price_rows_are_scoped_to_their_tenant(
    tenant: Any, other_tenant: Any, product: Any
) -> None:
    assert ProductPrice.objects.for_tenant(other_tenant).count() == 0
    assert ProductPrice.objects.for_tenant(tenant).filter(product=product).exists()
