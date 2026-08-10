"""Storefront catalog, search and favourites."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.catalog.constants import ProductStatus
from apps.catalog.models import Favorite, Product
from apps.catalog.search import search_products
from apps.catalog.services import archive_product, publish_product, toggle_favorite, unique_slug

pytestmark = pytest.mark.django_db


class TestPublicListing:
    def test_active_products_are_listed(self, api_client: APIClient, product: Any) -> None:
        response = api_client.get("/api/v1/catalog/products/")

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["price"]["price"] == "12.50"

    def test_drafts_are_hidden(self, api_client: APIClient, product_factory: Any) -> None:
        draft = product_factory(name="Rascunho")
        draft.status = ProductStatus.DRAFT
        draft.save()

        names = [row["name"] for row in api_client.get("/api/v1/catalog/products/").data["results"]]
        assert "Rascunho" not in names

    def test_out_of_stock_products_stay_visible(self, api_client: APIClient, product: Any) -> None:
        """Running out is not a reason to hide an item (spec §92)."""
        from apps.inventory.services import set_stock

        set_stock(product=product, quantity="0")

        row = api_client.get("/api/v1/catalog/products/").data["results"][0]
        assert row["stock"]["in_stock"] is False

    def test_cost_price_is_never_exposed(self, api_client: APIClient, product: Any) -> None:
        response = api_client.get(f"/api/v1/catalog/products/{product.slug}/")
        assert response.status_code == 200
        assert "cost_price" not in response.data
        assert "cost" not in str(response.data).lower().replace("cost_total", "")

    def test_exact_stock_levels_are_not_published(
        self, api_client: APIClient, product: Any
    ) -> None:
        row = api_client.get("/api/v1/catalog/products/").data["results"][0]
        assert set(row["stock"]) == {"in_stock", "low_stock"}

    def test_filter_by_category(
        self, api_client: APIClient, tenant: Any, category: Any, unit: Any, product: Any
    ) -> None:
        from apps.catalog.models import Category
        from conftest import make_product

        drinks = Category.objects.create(tenant=tenant, name="Bebidas", slug="bebidas")
        make_product(tenant=tenant, category=drinks, unit=unit, name="Suco")

        response = api_client.get("/api/v1/catalog/products/?category=bebidas")
        assert [row["name"] for row in response.data["results"]] == ["Suco"]

    def test_price_range_filter(self, api_client: APIClient, product_factory: Any) -> None:
        product_factory(name="Barato", price="3.00")
        product_factory(name="Caro", price="80.00")

        response = api_client.get("/api/v1/catalog/products/?max_price=5")
        assert [row["name"] for row in response.data["results"]] == ["Barato"]

    def test_sorting_by_price(self, api_client: APIClient, product_factory: Any) -> None:
        product_factory(name="Barato", price="3.00")
        product_factory(name="Caro", price="80.00")

        response = api_client.get("/api/v1/catalog/products/?sort=price")
        prices = [Decimal(row["price"]["price"]) for row in response.data["results"]]
        assert prices == sorted(prices)

    def test_unknown_sort_falls_back_instead_of_erroring(
        self, api_client: APIClient, product: Any
    ) -> None:
        """A crafted `sort` must not reach `order_by` and leak cost data."""
        response = api_client.get("/api/v1/catalog/products/?sort=cost_price")
        assert response.status_code == 200


class TestSearch:
    def test_finds_by_name_fragment(self, tenant: Any, product_factory: Any) -> None:
        product_factory(name="Pão Integral Teste")
        product_factory(name="Refrigerante Teste")

        results = search_products(Product.objects.filter(tenant=tenant), "integral")
        assert [row.name for row in results] == ["Pão Integral Teste"]

    def test_finds_by_sku(self, tenant: Any, product: Any) -> None:
        results = search_products(Product.objects.filter(tenant=tenant), product.sku)
        assert product.pk in {row.pk for row in results}

    def test_empty_term_returns_everything(self, tenant: Any, product: Any) -> None:
        queryset = Product.objects.filter(tenant=tenant)
        assert search_products(queryset, "").count() == queryset.count()

    def test_search_endpoint(self, api_client: APIClient, product_factory: Any) -> None:
        product_factory(name="Café Especial Teste")

        response = api_client.get("/api/v1/catalog/products/?q=café")
        assert response.status_code == 200
        assert any("Café" in row["name"] for row in response.data["results"])

    def test_suggestions_need_two_characters(self, api_client: APIClient, product: Any) -> None:
        assert api_client.get("/api/v1/catalog/search/suggestions/?q=a").data["suggestions"] == []


class TestFavorites:
    def test_toggle_adds_then_removes(self, customer: Any, product: Any) -> None:
        favorite, created = toggle_favorite(customer=customer, product=product)
        assert created is True and favorite is not None

        favorite, created = toggle_favorite(customer=customer, product=product)
        assert created is False and favorite is None
        assert Favorite.objects.count() == 0

    def test_api_toggle(self, customer_client: APIClient, product: Any) -> None:
        added = customer_client.post(
            "/api/v1/customers/me/favorites/", {"product": str(product.pk)}, format="json"
        )
        assert added.status_code == 201

        removed = customer_client.post(
            "/api/v1/customers/me/favorites/", {"product": str(product.pk)}, format="json"
        )
        assert removed.status_code == 204

    def test_listing_shows_only_own_favourites(
        self, customer_client: APIClient, customer: Any, product: Any, tenant: Any
    ) -> None:
        from apps.accounts.models import User

        other = User.objects.create_user(
            email="outro@example.test", password="senha-forte-4321", tenant=tenant
        )
        Favorite.objects.create(tenant=tenant, customer=other, product=product)
        Favorite.objects.create(tenant=tenant, customer=customer, product=product)

        response = customer_client.get("/api/v1/customers/me/favorites/")
        assert response.data["count"] == 1

    def test_anonymous_cannot_favourite(self, api_client: APIClient, product: Any) -> None:
        response = api_client.post(
            "/api/v1/customers/me/favorites/", {"product": str(product.pk)}, format="json"
        )
        assert response.status_code in (401, 403)


class TestProductLifecycle:
    def test_new_products_start_as_drafts(self, tenant: Any, category: Any, unit: Any) -> None:
        from apps.catalog.services import create_product

        product = create_product(tenant=tenant, name="Novo", category=category, sale_unit=unit)
        assert product.status == ProductStatus.DRAFT

    def test_cannot_publish_without_a_price(self, tenant: Any, category: Any, unit: Any) -> None:
        from apps.catalog.services import create_product
        from apps.common.exceptions import DomainError

        product = create_product(tenant=tenant, name="Sem preço", category=category, sale_unit=unit)
        with pytest.raises(DomainError) as exc:
            publish_product(product)
        assert exc.value.default_code == "PRODUCT_WITHOUT_PRICE"

    def test_deleting_archives_instead(self, admin_client_api: APIClient, product: Any) -> None:
        """Order history references products; they are never really deleted."""
        response = admin_client_api.delete(f"/api/v1/admin/products/{product.pk}/")
        assert response.status_code == 204

        product.refresh_from_db()
        assert product.status == ProductStatus.ARCHIVED
        assert Product.objects.filter(pk=product.pk).exists()

    def test_archived_products_leave_the_storefront(
        self, api_client: APIClient, product: Any
    ) -> None:
        archive_product(product)
        assert api_client.get("/api/v1/catalog/products/").data["count"] == 0

    def test_slugs_are_unique_per_tenant(self, tenant: Any, category: Any) -> None:
        from apps.catalog.models import Category

        first = unique_slug(Category, tenant.pk, "Mercearia")
        Category.objects.create(tenant=tenant, name="Mercearia 2", slug=first)
        second = unique_slug(Category, tenant.pk, "Mercearia")

        assert first != second


class TestAdminCatalog:
    def test_create_with_price_and_stock_in_one_call(
        self, admin_client_api: APIClient, category: Any, unit: Any
    ) -> None:
        response = admin_client_api.post(
            "/api/v1/admin/products/",
            {
                "name": "Produto Completo",
                "category": str(category.pk),
                "sale_unit": str(unit.pk),
                "base_price": "19.90",
                "cost_price": "11.00",
                "initial_stock": "25",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["base_price"] == "19.90"
        assert response.data["stock_quantity"] == "25.000"

    def test_staff_cannot_create_products(
        self, staff_client: APIClient, category: Any, unit: Any
    ) -> None:
        """The default staff role holds catalog.view but not catalog.create."""
        response = staff_client.post(
            "/api/v1/admin/products/",
            {"name": "Proibido", "category": str(category.pk), "sale_unit": str(unit.pk)},
            format="json",
        )
        assert response.status_code == 403

    def test_admin_sees_cost_and_stock(self, admin_client_api: APIClient, product: Any) -> None:
        response = admin_client_api.get(f"/api/v1/admin/products/{product.pk}/")
        assert response.data["cost_price"] == "8.00"
        assert response.data["available_quantity"] == "30.000"
