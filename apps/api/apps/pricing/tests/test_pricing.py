"""Pricing engine and price history."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.pricing.models import PriceHistory, ProductPrice
from apps.pricing.selectors import (
    MAX_PUBLIC_HISTORY_DAYS,
    PUBLIC_PRICE_FIELDS,
    annotate_effective_price,
    margin_metrics,
    public_price_series,
    resolve_price,
)
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


class TestPublicPriceSeries:
    """The series behind the product page chart.

    The point of these is the boundary: this data is served to anonymous
    shoppers, and the same table holds cost prices.
    """

    def test_cost_changes_never_appear(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="12.50", cost_price="9.99")

        series = public_price_series(product)
        prices = [point["price"] for point in series["points"]]

        assert "9.99" not in prices
        assert prices == ["12.50"]

    def test_only_allow_listed_fields_are_published(self) -> None:
        """A field is invisible until it is explicitly made public."""
        assert "cost_price" not in PUBLIC_PRICE_FIELDS
        assert set(PUBLIC_PRICE_FIELDS) == {"base_price", "sale_price"}

    def test_points_are_oldest_first(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="13.00")
        set_price(tenant=tenant, product=product, base_price="14.00")

        prices = [point["price"] for point in public_price_series(product)["points"]]
        assert prices == ["12.50", "13.00", "14.00"]

    def test_summary_reports_the_window(self, tenant: Any, product: Any) -> None:
        set_price(tenant=tenant, product=product, base_price="10.00")
        set_price(tenant=tenant, product=product, base_price="15.00")

        summary = public_price_series(product)["summary"]
        assert summary["lowest"] == "10.00"
        assert summary["highest"] == "15.00"
        assert summary["current"] == "15.00"
        # 12.50 -> 15.00
        assert summary["change_percentage"] == "20.00"

    def test_changes_outside_the_window_are_excluded(self, tenant: Any, product: Any) -> None:
        old = PriceHistory.objects.filter(product=product).first()
        PriceHistory.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )

        assert public_price_series(product, days=30)["points"] == []

    def test_window_is_clamped(self, product: Any) -> None:
        """A caller cannot ask for an unbounded scan."""
        assert public_price_series(product, days=99999)["days"] == MAX_PUBLIC_HISTORY_DAYS
        assert public_price_series(product, days=0)["days"] == 1

    def test_empty_history_still_reports_the_current_price(self, tenant: Any, product: Any) -> None:
        PriceHistory.objects.filter(product=product).delete()

        series = public_price_series(product)
        assert series["points"] == []
        assert series["summary"]["current"] == "12.50"
        assert series["summary"]["change_percentage"] is None


class TestPublicPriceHistoryEndpoint:
    def test_anonymous_shopper_can_read_it(self, api_client: Any, product: Any) -> None:
        response = api_client.get(f"/api/v1/catalog/products/{product.slug}/price-history/")

        assert response.status_code == 200
        assert response.data["points"][0]["price"] == "12.50"

    def test_response_carries_no_cost_or_margin(
        self, api_client: Any, tenant: Any, product: Any
    ) -> None:
        set_price(tenant=tenant, product=product, base_price="12.50", cost_price="7.77")

        body = str(api_client.get(f"/api/v1/catalog/products/{product.slug}/price-history/").data)

        assert "7.77" not in body
        for leak in ("cost", "margin", "markup"):
            assert leak not in body.lower()

    def test_unpublished_product_is_not_readable(
        self, api_client: Any, product_factory: Any
    ) -> None:
        """Visibility comes from the storefront queryset, not from this action."""
        hidden = product_factory(name="Rascunho", price="5.00", is_active=False)

        response = api_client.get(f"/api/v1/catalog/products/{hidden.slug}/price-history/")
        assert response.status_code == 404

    def test_other_tenants_product_is_not_readable(
        self, api_client: Any, other_tenant: Any
    ) -> None:
        from apps.catalog.models import Category, UnitOfMeasure
        from conftest import make_product

        foreign = make_product(
            tenant=other_tenant,
            category=Category.objects.create(tenant=other_tenant, name="Outro", slug="outro"),
            unit=UnitOfMeasure.objects.get(tenant=other_tenant, code="un"),
            name="Produto alheio",
            price="5.00",
        )

        # The client is pinned to the demo tenant; this product belongs to
        # another merchant and must not be reachable through it.
        response = api_client.get(f"/api/v1/catalog/products/{foreign.slug}/price-history/")
        assert response.status_code == 404


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
