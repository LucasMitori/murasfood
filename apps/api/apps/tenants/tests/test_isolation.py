"""
Tenant isolation.

Invariant #1: a user of tenant A can never read or write tenant B's data. These
tests attack it from several angles — spoofed headers, direct object ids, and
list endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class TestQuerysetScoping:
    def test_manager_for_tenant_filters(
        self, tenant: Any, other_tenant: Any, category: Any
    ) -> None:
        from apps.catalog.models import Category

        Category.objects.create(tenant=other_tenant, name="Outra", slug="outra")

        assert Category.objects.for_tenant(tenant).count() == 1
        assert Category.objects.for_tenant(other_tenant).count() == 1

    def test_for_tenant_with_none_returns_nothing(self, category: Any) -> None:
        """A missing tenant must never degrade into "return everything"."""
        from apps.catalog.models import Category

        assert Category.objects.for_tenant(None).count() == 0


class TestApiIsolation:
    def test_product_list_only_shows_own_tenant(
        self, api_client: APIClient, tenant: Any, other_tenant: Any, product: Any
    ) -> None:
        from apps.catalog.models import Category
        from conftest import make_product

        other_category = Category.objects.create(tenant=other_tenant, name="Beta", slug="beta-cat")
        other_unit = other_tenant.catalog_unitofmeasure_set.get(code="un")
        make_product(
            tenant=other_tenant,
            category=other_category,
            unit=other_unit,
            name="Produto da Beta",
        )

        response = api_client.get("/api/v1/catalog/products/")
        assert response.status_code == 200

        names = [row["name"] for row in response.data["results"]]
        assert product.name in names
        assert "Produto da Beta" not in names

    def test_header_cannot_move_an_authenticated_user(
        self, customer: Any, other_tenant: Any, product: Any
    ) -> None:
        """Spoofing X-Tenant must not grant access to another merchant."""
        client = APIClient()
        client.force_authenticate(user=customer)
        client.credentials(HTTP_X_TENANT=other_tenant.slug)

        response = client.get("/api/v1/catalog/products/")
        assert response.status_code == 200
        # The customer belongs to `tenant`, so they still see its catalog.
        assert [row["name"] for row in response.data["results"]] == [product.name]

    def test_cannot_fetch_another_tenants_order(
        self, tenant: Any, other_tenant: Any, customer: Any, other_customer: Any, product: Any
    ) -> None:
        from apps.cart.models import Cart
        from apps.cart.selectors import cart_queryset
        from apps.cart.services import add_item
        from apps.orders.services import create_order_from_cart

        cart = Cart.objects.create(tenant=tenant, customer=customer)
        add_item(cart=cart, product=product, quantity=1)
        order = create_order_from_cart(
            tenant=tenant,
            cart=cart_queryset().get(pk=cart.pk),
            delivery_method="PICKUP",
            customer=customer,
        )

        intruder = APIClient()
        intruder.force_authenticate(user=other_customer)
        intruder.credentials(HTTP_X_TENANT=other_tenant.slug)

        response = intruder.get(f"/api/v1/orders/{order.number}/")
        assert response.status_code == 404

    def test_admin_cannot_read_other_tenant_customers(
        self, admin_client_api: APIClient, other_customer: Any, customer: Any
    ) -> None:
        response = admin_client_api.get("/api/v1/admin/customers/")
        assert response.status_code == 200

        emails = [row["email"] for row in response.data["results"]]
        assert customer.email in emails
        # Both customers share an address; only ours may appear.
        assert len(emails) == 1


class TestUserUniqueness:
    def test_same_email_allowed_in_two_tenants(self, customer: Any, other_customer: Any) -> None:
        """The same person may shop at two merchants on one deployment."""
        assert customer.email == other_customer.email
        assert customer.tenant_id != other_customer.tenant_id

    def test_duplicate_email_within_a_tenant_is_rejected(self, tenant: Any, customer: Any) -> None:
        from django.db import IntegrityError

        from apps.accounts.models import User

        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email=customer.email, password="outra-senha-1234", tenant=tenant
            )
