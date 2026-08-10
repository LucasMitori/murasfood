"""
Shared pytest fixtures.

Two tenants exist in most fixtures on purpose: the second one is what makes
tenant-isolation tests meaningful. A test that only ever sees one tenant cannot
prove that data does not leak between them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _media_root(settings: Any, tmp_path: Any) -> None:
    """Keep uploads inside the test's temporary directory."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGE_BACKEND = "local"
    settings.S3_ENDPOINT = ""

    from apps.media.storage import reset_storage_cache

    reset_storage_cache()


@pytest.fixture
def tenant(db: Any) -> Any:
    """A fully provisioned demo tenant."""
    from apps.tenants.bootstrap import bootstrap_tenant
    from apps.tenants.services import create_tenant

    created = create_tenant(
        legal_name="Loja Alfa LTDA",
        trade_name="Loja Alfa",
        support_email="alfa@example.test",
        slug="alfa",
        city="Cidade Exemplo",
        state="SP",
    )
    bootstrap_tenant(created)
    return created


@pytest.fixture
def other_tenant(db: Any) -> Any:
    """A second merchant, used to prove isolation."""
    from apps.tenants.bootstrap import bootstrap_tenant
    from apps.tenants.services import create_tenant

    created = create_tenant(
        legal_name="Loja Beta LTDA",
        trade_name="Loja Beta",
        support_email="beta@example.test",
        slug="beta",
        city="Outra Cidade",
        state="RJ",
    )
    bootstrap_tenant(created)
    return created


@pytest.fixture
def customer(tenant: Any) -> Any:
    from apps.accounts.constants import UserType
    from apps.accounts.models import User

    return User.objects.create_user(
        email="cliente@example.test",
        password="senha-super-secreta-1",
        tenant=tenant,
        first_name="Carlos",
        last_name="Cliente",
        user_type=UserType.CUSTOMER,
        is_verified=True,
    )


@pytest.fixture
def other_customer(other_tenant: Any) -> Any:
    from apps.accounts.constants import UserType
    from apps.accounts.models import User

    return User.objects.create_user(
        email="cliente@example.test",  # same address, different tenant
        password="senha-super-secreta-2",
        tenant=other_tenant,
        user_type=UserType.CUSTOMER,
        is_verified=True,
    )


@pytest.fixture
def admin_user(tenant: Any) -> Any:
    """A tenant administrator: holds every permission code."""
    from apps.accounts.constants import UserType
    from apps.accounts.models import User

    return User.objects.create_user(
        email="admin@example.test",
        password="senha-super-secreta-3",
        tenant=tenant,
        user_type=UserType.ADMINISTRATOR,
        is_verified=True,
    )


@pytest.fixture
def staff_user(tenant: Any) -> Any:
    """A staff member with the default staff role only."""
    from apps.accounts.constants import SystemRole, UserType
    from apps.accounts.models import Role, User
    from apps.accounts.services import assign_role

    user = User.objects.create_user(
        email="equipe@example.test",
        password="senha-super-secreta-4",
        tenant=tenant,
        user_type=UserType.STAFF,
        is_verified=True,
    )
    assign_role(user, Role.objects.get(tenant=tenant, slug=SystemRole.STAFF))
    return user


@pytest.fixture
def unit(tenant: Any) -> Any:
    from apps.catalog.models import UnitOfMeasure

    return UnitOfMeasure.objects.get(tenant=tenant, code="un")


@pytest.fixture
def weight_unit(tenant: Any) -> Any:
    from apps.catalog.models import UnitOfMeasure

    return UnitOfMeasure.objects.get(tenant=tenant, code="kg")


@pytest.fixture
def category(tenant: Any) -> Any:
    from apps.catalog.models import Category

    return Category.objects.create(tenant=tenant, name="Mercearia", slug="mercearia")


def make_product(
    *,
    tenant: Any,
    category: Any,
    unit: Any,
    name: str = "Produto Teste",
    price: str = "10.00",
    cost: str | None = "6.00",
    stock: str = "20",
    **kwargs: Any,
) -> Any:
    """Create an active, priced, in-stock product.

    A helper rather than a fixture so a test can create several products
    without repeating the price/stock wiring each time.
    """
    from apps.catalog.constants import ProductStatus
    from apps.catalog.services import create_product
    from apps.inventory.services import set_stock
    from apps.pricing.services import set_price

    product = create_product(
        tenant=tenant,
        name=name,
        category=category,
        sale_unit=unit,
        status=ProductStatus.ACTIVE,
        **kwargs,
    )
    set_price(tenant=tenant, product=product, base_price=price, cost_price=cost)
    set_stock(product=product, quantity=stock)
    product.refresh_from_db()
    return product


@pytest.fixture
def product_factory(tenant: Any, category: Any, unit: Any) -> Any:
    """Callable factory bound to the default tenant/category/unit."""

    def factory(**kwargs: Any) -> Any:
        kwargs.setdefault("tenant", tenant)
        kwargs.setdefault("category", category)
        kwargs.setdefault("unit", unit)
        return make_product(**kwargs)

    return factory


@pytest.fixture
def product(product_factory: Any) -> Any:
    return product_factory(name="Arroz Teste 1kg", price="12.50", cost="8.00", stock="30")


@pytest.fixture
def api_client(tenant: Any) -> APIClient:
    """Anonymous client pinned to the primary tenant."""
    client = APIClient()
    client.credentials(HTTP_X_TENANT=tenant.slug)
    return client


@pytest.fixture
def customer_client(tenant: Any, customer: Any) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_TENANT=tenant.slug)
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def admin_client_api(tenant: Any, admin_user: Any) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_TENANT=tenant.slug)
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def staff_client(tenant: Any, staff_user: Any) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_TENANT=tenant.slug)
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def address(tenant: Any, customer: Any) -> Any:
    from apps.accounts.services import create_address

    return create_address(
        customer=customer,
        tenant=tenant,
        label="Casa",
        recipient_name="Carlos Cliente",
        postal_code="01002000",
        street="Rua de Teste",
        number="42",
        neighborhood="Bairro Teste",
        city="Cidade Exemplo",
        state="SP",
    )


@pytest.fixture
def filled_cart(tenant: Any, customer: Any, product: Any) -> Any:
    """A customer cart holding two units of ``product``."""
    from apps.cart.models import Cart
    from apps.cart.selectors import cart_queryset
    from apps.cart.services import add_item

    cart = Cart.objects.create(tenant=tenant, customer=customer)
    add_item(cart=cart, product=product, quantity=Decimal("2"))
    return cart_queryset().get(pk=cart.pk)
