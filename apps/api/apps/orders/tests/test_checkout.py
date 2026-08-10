"""
Checkout.

The properties under test are the ones that protect money: prices are taken
from the server, totals are derived, stock is reserved atomically, and the
whole thing is idempotent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.common.exceptions import InsufficientStockError
from apps.orders.constants import OrderStatus
from apps.orders.models import Order
from apps.orders.services import EmptyCartError, create_order_from_cart

pytestmark = pytest.mark.django_db


class TestOrderCreation:
    def test_totals_are_derived_from_the_lines(
        self, tenant: Any, customer: Any, filled_cart: Any
    ) -> None:
        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )

        assert order.subtotal == Decimal("25.00")  # 2 × 12.50
        assert order.delivery_fee == Decimal("0.00")  # pickup
        assert order.total == Decimal("25.00")
        assert order.status == OrderStatus.PENDING_PAYMENT

    def test_items_store_immutable_snapshots(
        self, tenant: Any, customer: Any, filled_cart: Any, product: Any
    ) -> None:
        """Invariant #3: a later price change must not rewrite an old order."""
        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )
        item = order.items.first()

        assert item.product_name == product.name
        assert item.product_sku == product.sku
        assert item.unit_price == Decimal("12.50")
        assert item.unit_cost == Decimal("8.00")

        from apps.pricing.services import set_price

        set_price(tenant=tenant, product=product, base_price="99.00")

        item.refresh_from_db()
        assert item.unit_price == Decimal("12.50")
        order.refresh_from_db()
        assert order.total == Decimal("25.00")

    def test_stock_is_reserved_not_consumed(
        self, tenant: Any, customer: Any, filled_cart: Any, product: Any
    ) -> None:
        from apps.inventory.models import InventoryItem

        create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )

        item = InventoryItem.objects.get(product=product)
        assert item.quantity == Decimal("30.000")
        assert item.reserved_quantity == Decimal("2.000")

    def test_empty_cart_is_rejected(self, tenant: Any, customer: Any) -> None:
        from apps.cart.models import Cart
        from apps.cart.selectors import cart_queryset

        cart = Cart.objects.create(tenant=tenant, customer=customer)

        with pytest.raises(EmptyCartError):
            create_order_from_cart(
                tenant=tenant,
                cart=cart_queryset().get(pk=cart.pk),
                delivery_method="PICKUP",
                customer=customer,
            )

    def test_checkout_fails_when_stock_ran_out_meanwhile(
        self, tenant: Any, customer: Any, product_factory: Any
    ) -> None:
        """Another shopper took the last unit between cart view and checkout.

        Checkout refuses at its validation pass and names the offending line, so
        the customer is told which item is the problem. The lock-level guard
        behind it is covered by the inventory reservation tests.
        """
        from apps.cart.models import Cart
        from apps.cart.selectors import cart_queryset
        from apps.cart.services import add_item
        from apps.inventory.services import reserve_stock
        from apps.orders.services import CheckoutValidationError

        scarce = product_factory(name="Peça única", stock="1")
        cart = Cart.objects.create(tenant=tenant, customer=customer)
        add_item(cart=cart, product=scarce, quantity=1)

        reserve_stock(product=scarce, quantity="1")  # someone else got there first

        with pytest.raises((CheckoutValidationError, InsufficientStockError)) as exc:
            create_order_from_cart(
                tenant=tenant,
                cart=cart_queryset().get(pk=cart.pk),
                delivery_method="PICKUP",
                customer=customer,
            )
        assert "Peça única" in str(exc.value.details)

    def test_delivery_requires_an_address(
        self, tenant: Any, customer: Any, filled_cart: Any
    ) -> None:
        from apps.orders.services import CheckoutValidationError

        with pytest.raises(CheckoutValidationError):
            create_order_from_cart(
                tenant=tenant, cart=filled_cart, delivery_method="DELIVERY", customer=customer
            )

    def test_delivery_fee_comes_from_the_server(
        self, tenant: Any, customer: Any, filled_cart: Any, address: Any
    ) -> None:
        from apps.delivery.selectors import get_settings

        settings_row = get_settings(tenant)
        settings_row.base_fee = Decimal("7.90")
        settings_row.save()

        order = create_order_from_cart(
            tenant=tenant,
            cart=filled_cart,
            delivery_method="DELIVERY",
            address=address,
            customer=customer,
        )

        assert order.delivery_fee == Decimal("7.90")
        assert order.total == Decimal("32.90")
        assert order.address.street == address.street

    def test_order_numbers_are_unique_per_tenant(
        self, tenant: Any, customer: Any, product: Any
    ) -> None:
        from apps.cart.models import Cart
        from apps.cart.selectors import cart_queryset
        from apps.cart.services import add_item

        numbers = set()
        for _ in range(5):
            cart = Cart.objects.create(tenant=tenant, customer=customer)
            add_item(cart=cart, product=product, quantity=1)
            order = create_order_from_cart(
                tenant=tenant,
                cart=cart_queryset().get(pk=cart.pk),
                delivery_method="PICKUP",
                customer=customer,
            )
            numbers.add(order.number)

        assert len(numbers) == 5


class TestCheckoutApi:
    def _prepare_cart(self, client: APIClient, product: Any) -> None:
        response = client.post(
            "/api/v1/cart/items/", {"product": str(product.pk), "quantity": "2"}, format="json"
        )
        assert response.status_code == 201

    def test_checkout_creates_an_order_and_a_payment(
        self, customer_client: APIClient, product: Any
    ) -> None:
        self._prepare_cart(customer_client, product)

        response = customer_client.post(
            "/api/v1/orders/checkout/", {"delivery_method": "PICKUP"}, format="json"
        )
        assert response.status_code == 201
        assert response.data["status"] == OrderStatus.PENDING_PAYMENT
        assert response.data["payment"]["pix_payload"]

    def test_client_supplied_totals_are_ignored(
        self, customer_client: APIClient, product: Any
    ) -> None:
        """Invariant #2: the customer cannot set their own price."""
        self._prepare_cart(customer_client, product)

        response = customer_client.post(
            "/api/v1/orders/checkout/",
            {"delivery_method": "PICKUP", "total": "0.01", "subtotal": "0.01"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["total"] == "25.00"

    def test_repeated_idempotency_key_returns_the_same_order(
        self, customer_client: APIClient, product: Any
    ) -> None:
        self._prepare_cart(customer_client, product)

        payload = {"delivery_method": "PICKUP"}
        first = customer_client.post(
            "/api/v1/orders/checkout/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-key-1",
        )
        second = customer_client.post(
            "/api/v1/orders/checkout/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-key-1",
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.data["number"] == second.data["number"]
        assert Order.objects.count() == 1

    def test_reused_key_with_different_payload_is_rejected(
        self, customer_client: APIClient, product: Any, address: Any
    ) -> None:
        self._prepare_cart(customer_client, product)

        customer_client.post(
            "/api/v1/orders/checkout/",
            {"delivery_method": "PICKUP"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-key-2",
        )
        conflict = customer_client.post(
            "/api/v1/orders/checkout/",
            {"delivery_method": "DELIVERY", "address": str(address.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-key-2",
        )

        assert conflict.status_code == 409
        assert conflict.data["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_anonymous_checkout_is_refused(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/api/v1/orders/checkout/", {"delivery_method": "PICKUP"}, format="json"
        )
        assert response.status_code in (401, 403)
