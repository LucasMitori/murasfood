"""
Cart behaviour.

The property that matters most: a cart holds *intent*, not prices. Prices are
re-resolved on every read, so a cart left open overnight cannot lock in
yesterday's price (spec §15).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem, CartStatus
from apps.cart.selectors import cart_queryset, cart_totals, unavailable_items
from apps.cart.services import CartError, add_item, merge_carts, set_item_quantity
from apps.common.exceptions import InsufficientStockError

pytestmark = pytest.mark.django_db


class TestCartItems:
    def test_adding_twice_increases_the_quantity(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        cart = Cart.objects.create(tenant=tenant, customer=customer)
        add_item(cart=cart, product=product, quantity=2)
        add_item(cart=cart, product=product, quantity=3)

        assert CartItem.objects.filter(cart=cart).count() == 1
        assert CartItem.objects.get(cart=cart).quantity == Decimal("5.000")

    def test_cannot_add_more_than_available(self, tenant: Any, customer: Any, product: Any) -> None:
        cart = Cart.objects.create(tenant=tenant, customer=customer)

        with pytest.raises(InsufficientStockError):
            add_item(cart=cart, product=product, quantity=999)

    def test_unit_products_reject_fractional_quantities(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        cart = Cart.objects.create(tenant=tenant, customer=customer)

        with pytest.raises(CartError) as exc:
            add_item(cart=cart, product=product, quantity=Decimal("1.5"))
        assert exc.value.default_code == "FRACTIONAL_NOT_ALLOWED"

    def test_weighed_products_accept_fractional_quantities(
        self, tenant: Any, customer: Any, category: Any, weight_unit: Any
    ) -> None:
        """A bakery selling by the kilo must handle 1.350 kg (spec §91)."""
        from apps.catalog.constants import ProductType
        from conftest import make_product

        bread = make_product(
            tenant=tenant,
            category=category,
            unit=weight_unit,
            name="Pão por peso",
            price="16.50",
            stock="20.000",
            product_type=ProductType.WEIGHTED,
        )

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        item = add_item(cart=cart, product=bread, quantity=Decimal("1.350"))

        assert item.quantity == Decimal("1.350")
        assert item.line_total == Decimal("22.28")

    def test_setting_quantity_to_zero_removes_the_line(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        cart = Cart.objects.create(tenant=tenant, customer=customer)
        item = add_item(cart=cart, product=product, quantity=2)

        assert set_item_quantity(cart=cart, item=item, quantity=0) is None
        assert CartItem.objects.filter(cart=cart).count() == 0

    def test_per_order_limit_is_enforced(self, tenant: Any, customer: Any, product: Any) -> None:
        product.max_quantity_per_order = Decimal("3.000")
        product.save()

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        with pytest.raises(CartError) as exc:
            add_item(cart=cart, product=product, quantity=5)
        assert exc.value.default_code == "QUANTITY_LIMIT_EXCEEDED"


class TestPricingIsLive:
    def test_price_change_is_reflected_in_the_cart(
        self, tenant: Any, filled_cart: Any, product: Any
    ) -> None:
        from apps.pricing.services import set_price

        assert filled_cart.subtotal == Decimal("25.00")

        set_price(tenant=tenant, product=product, base_price="20.00")

        refreshed = cart_queryset().get(pk=filled_cart.pk)
        assert refreshed.subtotal == Decimal("40.00")

    def test_cart_items_have_no_stored_price_column(self) -> None:
        """Guards the design decision, not just the current behaviour."""
        field_names = {field.name for field in CartItem._meta.get_fields()}
        assert "unit_price" not in field_names
        assert "line_total" not in field_names


class TestTotals:
    def test_empty_cart_totals_are_zero(self) -> None:
        totals = cart_totals(None)
        assert totals["subtotal"] == "0.00"
        assert totals["total"] == "0.00"
        assert totals["item_count"] == 0

    def test_discounts_and_delivery_are_included(
        self, tenant: Any, filled_cart: Any, address: Any
    ) -> None:
        from apps.delivery.selectors import get_settings
        from apps.promotions.models import DiscountType, Promotion

        Promotion.objects.create(
            tenant=tenant,
            name="10%",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
        )
        settings_row = get_settings(tenant)
        settings_row.base_fee = Decimal("7.90")
        settings_row.save()

        totals = cart_totals(
            filled_cart, delivery_method="DELIVERY", postal_code=address.postal_code
        )
        assert totals["subtotal"] == "25.00"
        assert totals["discount"] == "2.50"
        assert totals["delivery_fee"] == "7.90"
        assert totals["total"] == "30.40"

    def test_free_delivery_threshold_zeroes_the_fee(
        self, tenant: Any, customer: Any, product: Any, address: Any
    ) -> None:
        from apps.delivery.selectors import get_settings

        settings_row = get_settings(tenant)
        settings_row.base_fee = Decimal("7.90")
        settings_row.free_delivery_threshold = Decimal("50.00")
        settings_row.save()

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        add_item(cart=cart, product=product, quantity=8)  # 8 × 12.50 = 100.00

        totals = cart_totals(
            cart_queryset().get(pk=cart.pk),
            delivery_method="DELIVERY",
            postal_code=address.postal_code,
        )
        assert totals["delivery_fee"] == "0.00"


class TestIssues:
    def test_out_of_stock_line_is_surfaced(
        self, tenant: Any, filled_cart: Any, product: Any
    ) -> None:
        from apps.inventory.services import set_stock

        set_stock(product=product, quantity="0")

        problems = unavailable_items(cart_queryset().get(pk=filled_cart.pk))
        assert problems and problems[0]["reason"] == "OUT_OF_STOCK"

    def test_archived_product_is_surfaced(self, filled_cart: Any, product: Any) -> None:
        from apps.catalog.services import archive_product

        archive_product(product)

        problems = unavailable_items(cart_queryset().get(pk=filled_cart.pk))
        assert problems and problems[0]["reason"] == "UNAVAILABLE"


class TestMerge:
    def test_anonymous_cart_folds_into_the_customer_cart(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        anonymous = Cart.objects.create(tenant=tenant)
        add_item(cart=anonymous, product=product, quantity=2)

        existing = Cart.objects.create(tenant=tenant, customer=customer)
        add_item(cart=existing, product=product, quantity=1)

        merged = merge_carts(anonymous_cart=anonymous, customer=customer)
        anonymous.refresh_from_db()

        assert merged.pk == existing.pk
        assert CartItem.objects.get(cart=merged).quantity == Decimal("3.000")
        assert anonymous.status == CartStatus.MERGED

    def test_anonymous_cart_is_adopted_when_none_exists(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        anonymous = Cart.objects.create(tenant=tenant)
        add_item(cart=anonymous, product=product, quantity=2)

        merged = merge_carts(anonymous_cart=anonymous, customer=customer)
        assert merged.pk == anonymous.pk
        assert merged.customer_id == customer.pk


class TestCartApi:
    def test_anonymous_cart_returns_a_token(self, api_client: APIClient, product: Any) -> None:
        response = api_client.post(
            "/api/v1/cart/items/", {"product": str(product.pk), "quantity": "1"}, format="json"
        )
        assert response.status_code == 201
        assert response["X-Cart-Token"]

    def test_token_recovers_the_same_cart(self, api_client: APIClient, product: Any) -> None:
        created = api_client.post(
            "/api/v1/cart/items/", {"product": str(product.pk), "quantity": "1"}, format="json"
        )
        token = created["X-Cart-Token"]

        api_client.credentials(HTTP_X_TENANT=product.tenant.slug, HTTP_X_CART_TOKEN=token)
        response = api_client.get("/api/v1/cart/")

        assert response.status_code == 200
        assert response.data["id"] == created.data["id"]
        assert len(response.data["items"]) == 1

    def test_customer_cart_is_scoped_to_the_account(
        self, customer_client: APIClient, product: Any
    ) -> None:
        customer_client.post(
            "/api/v1/cart/items/", {"product": str(product.pk), "quantity": "2"}, format="json"
        )
        response = customer_client.get("/api/v1/cart/")

        assert response.data["totals"]["subtotal"] == "25.00"
        assert response.data["items"][0]["quantity"] == "2.000"

    def test_cannot_add_another_tenants_product(
        self, customer_client: APIClient, other_tenant: Any, unit: Any
    ) -> None:
        from apps.catalog.models import Category
        from conftest import make_product

        foreign_category = Category.objects.create(tenant=other_tenant, name="Beta", slug="beta-x")
        foreign_unit = other_tenant.catalog_unitofmeasure_set.get(code="un")
        foreign = make_product(
            tenant=other_tenant, category=foreign_category, unit=foreign_unit, name="Alheio"
        )

        response = customer_client.post(
            "/api/v1/cart/items/", {"product": str(foreign.pk)}, format="json"
        )
        assert response.status_code == 404

    def test_clearing_empties_the_cart(self, customer_client: APIClient, product: Any) -> None:
        customer_client.post(
            "/api/v1/cart/items/", {"product": str(product.pk), "quantity": "1"}, format="json"
        )
        response = customer_client.delete("/api/v1/cart/")

        assert response.status_code == 200
        assert response.data["items"] == []
