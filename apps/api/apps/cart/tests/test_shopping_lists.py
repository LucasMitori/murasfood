"""Shopping lists: reusable sets of products a customer buys regularly."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.cart.models import ShoppingList, ShoppingListItem
from apps.cart.services import (
    ShoppingListError,
    add_list_to_cart,
    create_list_from_cart,
    create_shopping_list,
    set_list_item,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shopping_list(tenant: Any, customer: Any) -> Any:
    return create_shopping_list(tenant=tenant, customer=customer, name="Mensal")


class TestListManagement:
    def test_name_must_be_unique_per_customer(self, tenant: Any, customer: Any) -> None:
        create_shopping_list(tenant=tenant, customer=customer, name="Mensal")

        with pytest.raises(ShoppingListError, match="already have a list"):
            create_shopping_list(tenant=tenant, customer=customer, name="mensal")

    def test_two_customers_may_use_the_same_name(
        self, tenant: Any, customer: Any, staff_user: Any
    ) -> None:
        create_shopping_list(tenant=tenant, customer=customer, name="Mensal")
        create_shopping_list(tenant=tenant, customer=staff_user, name="Mensal")

        assert ShoppingList.objects.filter(name="Mensal").count() == 2

    def test_blank_name_is_rejected(self, tenant: Any, customer: Any) -> None:
        with pytest.raises(ShoppingListError, match="name"):
            create_shopping_list(tenant=tenant, customer=customer, name="   ")


class TestListItems:
    def test_adding_the_same_product_twice_sets_rather_than_stacks(
        self, shopping_list: Any, product: Any
    ) -> None:
        """A list is a plan, so a repeated add is a correction, not an increment.

        The cart deliberately behaves the other way round.
        """
        set_list_item(shopping_list=shopping_list, product=product, quantity=2)
        set_list_item(shopping_list=shopping_list, product=product, quantity=5)

        items = ShoppingListItem.objects.filter(shopping_list=shopping_list)
        assert items.count() == 1
        assert items.first().quantity == Decimal("5.000")

    def test_out_of_stock_products_can_still_be_planned(
        self, shopping_list: Any, product: Any
    ) -> None:
        """Availability belongs to the cart, not to a plan for next month."""
        from apps.inventory.services import set_stock

        set_stock(product=product, quantity="0")

        item = set_list_item(shopping_list=shopping_list, product=product, quantity=3)
        assert item.quantity == Decimal("3.000")
        assert item.is_available is False

    def test_whole_unit_products_reject_fractions(self, shopping_list: Any, product: Any) -> None:
        with pytest.raises(ShoppingListError, match="whole units"):
            set_list_item(shopping_list=shopping_list, product=product, quantity="1.5")

    def test_zero_quantity_is_rejected(self, shopping_list: Any, product: Any) -> None:
        with pytest.raises(ShoppingListError, match="greater than zero"):
            set_list_item(shopping_list=shopping_list, product=product, quantity=0)

    def test_product_from_another_tenant_is_refused(
        self, shopping_list: Any, other_tenant: Any
    ) -> None:
        from apps.catalog.models import Category, UnitOfMeasure
        from conftest import make_product

        foreign = make_product(
            tenant=other_tenant,
            category=Category.objects.create(tenant=other_tenant, name="Outro", slug="outro"),
            unit=UnitOfMeasure.objects.get(tenant=other_tenant, code="un"),
            name="Alheio",
        )

        with pytest.raises(ShoppingListError):
            set_list_item(shopping_list=shopping_list, product=foreign, quantity=1)


class TestAddToCart:
    def test_items_land_in_the_cart(
        self, tenant: Any, customer: Any, shopping_list: Any, product: Any
    ) -> None:
        from apps.cart.models import Cart

        set_list_item(shopping_list=shopping_list, product=product, quantity=3)
        cart = Cart.objects.create(tenant=tenant, customer=customer)

        result = add_list_to_cart(shopping_list=shopping_list, cart=cart)

        assert result["added_count"] == 1
        assert result["skipped_count"] == 0
        assert cart.items.first().quantity == Decimal("3.000")

    def test_unavailable_lines_are_skipped_and_the_rest_still_go_in(
        self, tenant: Any, customer: Any, shopping_list: Any, product_factory: Any
    ) -> None:
        """The reason partial success exists: one gap must not block the shop."""
        from apps.cart.models import Cart
        from apps.inventory.services import set_stock

        available = product_factory(name="Disponível", price="4.00", stock="10")
        missing = product_factory(name="Esgotado", price="6.00", stock="10")
        set_stock(product=missing, quantity="0")

        set_list_item(shopping_list=shopping_list, product=available, quantity=2)
        set_list_item(shopping_list=shopping_list, product=missing, quantity=1)

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        result = add_list_to_cart(shopping_list=shopping_list, cart=cart)

        assert result["added_count"] == 1
        assert result["skipped_count"] == 1
        assert result["skipped"][0]["product"] == "Esgotado"
        assert cart.items.count() == 1

    def test_skipped_lines_say_why(
        self, tenant: Any, customer: Any, shopping_list: Any, product: Any
    ) -> None:
        """A silent drop would leave the customer short at the till."""
        from apps.cart.models import Cart
        from apps.catalog.constants import ProductStatus

        set_list_item(shopping_list=shopping_list, product=product, quantity=1)
        product.status = ProductStatus.ARCHIVED
        product.save(update_fields=["status"])

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        result = add_list_to_cart(shopping_list=shopping_list, cart=cart)

        assert result["skipped_count"] == 1
        assert result["skipped"][0]["reason"]
        assert result["skipped"][0]["detail"]

    def test_adding_twice_does_not_double_beyond_the_list(
        self, tenant: Any, customer: Any, shopping_list: Any, product: Any
    ) -> None:
        """Copying is an add, so a second copy stacks — the cart's own rule."""
        from apps.cart.models import Cart

        set_list_item(shopping_list=shopping_list, product=product, quantity=2)
        cart = Cart.objects.create(tenant=tenant, customer=customer)

        add_list_to_cart(shopping_list=shopping_list, cart=cart)
        add_list_to_cart(shopping_list=shopping_list, cart=cart)

        assert cart.items.first().quantity == Decimal("4.000")


class TestSaveCartAsList:
    def test_cart_contents_become_a_list(
        self, tenant: Any, customer: Any, filled_cart: Any
    ) -> None:
        created = create_list_from_cart(cart=filled_cart, customer=customer, name="Compra do mês")

        assert created.items.count() == filled_cart.items.count()
        assert created.items.first().quantity == filled_cart.items.first().quantity

    def test_duplicate_name_is_refused_before_copying(
        self, tenant: Any, customer: Any, filled_cart: Any
    ) -> None:
        create_shopping_list(tenant=tenant, customer=customer, name="Mensal")

        with pytest.raises(ShoppingListError):
            create_list_from_cart(cart=filled_cart, customer=customer, name="Mensal")

        assert ShoppingListItem.objects.count() == 0


class TestShoppingListApi:
    def test_lists_are_private_to_their_owner(
        self, tenant: Any, customer_client: Any, staff_user: Any
    ) -> None:
        """The isolation that matters: same tenant, different shopper."""
        other = create_shopping_list(tenant=tenant, customer=staff_user, name="Do colega")

        assert customer_client.get(f"/api/v1/shopping-lists/{other.pk}/").status_code == 404
        assert (
            customer_client.patch(
                f"/api/v1/shopping-lists/{other.pk}/", {"name": "Sequestrada"}, format="json"
            ).status_code
            == 404
        )
        assert customer_client.delete(f"/api/v1/shopping-lists/{other.pk}/").status_code == 404

        other.refresh_from_db()
        assert other.name == "Do colega"

    def test_anonymous_visitors_are_refused(self, api_client: Any) -> None:
        assert api_client.get("/api/v1/shopping-lists/").status_code == 401

    def test_create_and_read_back(self, customer_client: Any, product: Any) -> None:
        created = customer_client.post(
            "/api/v1/shopping-lists/", {"name": "Semanal"}, format="json"
        )
        assert created.status_code == 201

        list_id = created.data["id"]
        added = customer_client.post(
            f"/api/v1/shopping-lists/{list_id}/items/",
            {"product": str(product.pk), "quantity": "2"},
            format="json",
        )

        assert added.status_code == 201
        assert added.data["item_count"] == 1
        assert added.data["estimated_total"] == "25.00"

    def test_index_reports_counts_without_the_lines(
        self, customer_client: Any, shopping_list: Any, product: Any
    ) -> None:
        set_list_item(shopping_list=shopping_list, product=product, quantity=2)

        response = customer_client.get("/api/v1/shopping-lists/")

        assert response.status_code == 200
        assert response.data[0]["item_count"] == 1
        assert "items" not in response.data[0]

    def test_add_to_cart_endpoint_reports_both_halves(
        self, customer_client: Any, shopping_list: Any, product: Any
    ) -> None:
        set_list_item(shopping_list=shopping_list, product=product, quantity=2)

        response = customer_client.post(f"/api/v1/shopping-lists/{shopping_list.pk}/add-to-cart/")

        assert response.status_code == 200
        assert response.data["added_count"] == 1
        assert response.data["skipped"] == []

    def test_saving_an_empty_cart_is_refused(self, customer_client: Any) -> None:
        response = customer_client.post(
            "/api/v1/shopping-lists/from-cart/", {"name": "Vazia"}, format="json"
        )
        assert response.status_code == 404

    def test_from_cart_is_not_read_as_a_list_id(self, customer_client: Any) -> None:
        """Route ordering: the literal segment must win over `<uuid:list_id>`."""
        response = customer_client.post(
            "/api/v1/shopping-lists/from-cart/", {"name": "Qualquer"}, format="json"
        )
        assert response.status_code != 405
