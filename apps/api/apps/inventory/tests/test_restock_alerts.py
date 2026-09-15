"""
Back-in-stock alerts.

The feature only earns its place if two things hold: the notice actually goes
out when stock returns, and it goes out *once*. Everything here is about one of
those two, or about the ways a signup endpoint open to anonymous callers can be
abused.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.inventory.models import RestockAlert
from apps.inventory.services import (
    adjust_stock,
    restock_demand,
    set_stock,
    subscribe_to_restock,
    unsubscribe_from_restock,
)

pytestmark = pytest.mark.django_db


def endpoint(product: Any) -> str:
    return f"/api/v1/catalog/products/{product.slug}/restock-alert/"


def empty(product: Any) -> None:
    """Drive the product to zero available."""
    set_stock(product=product, quantity=Decimal("0"))


class TestSubscribing:
    def test_a_visitor_can_subscribe_without_an_account(
        self, api_client: Any, product: Any
    ) -> None:
        """The whole point: an account requirement collects no signal at all."""
        empty(product)

        response = api_client.post(
            endpoint(product), {"email": "visitante@exemplo.com.br"}, format="json"
        )

        assert response.status_code == 201
        assert response.json()["subscribed"] is True
        assert RestockAlert.objects.filter(product=product).count() == 1

    def test_subscribing_twice_does_not_make_two_rows(self, api_client: Any, product: Any) -> None:
        """Otherwise one impatient shopper gets two emails and counts twice in
        the demand report."""
        empty(product)

        for _ in range(3):
            api_client.post(endpoint(product), {"email": "a@exemplo.com"}, format="json")

        assert RestockAlert.objects.filter(product=product).count() == 1

    def test_an_address_is_required_when_nobody_is_signed_in(
        self, api_client: Any, product: Any
    ) -> None:
        empty(product)

        response = api_client.post(endpoint(product), {}, format="json")

        assert response.status_code == 400

    def test_a_signed_in_customer_cannot_subscribe_a_stranger(
        self, customer_client: Any, customer: Any, product: Any
    ) -> None:
        """An authenticated caller naming someone else's address would turn this
        into a way to send mail to arbitrary people."""
        empty(product)

        customer_client.post(endpoint(product), {"email": "vitima@exemplo.com"}, format="json")

        alert = RestockAlert.objects.get(product=product)
        assert alert.customer_id == customer.pk
        assert alert.recipient == customer.email

    def test_unsubscribing_removes_the_row(self, api_client: Any, product: Any) -> None:
        empty(product)
        api_client.post(endpoint(product), {"email": "a@exemplo.com"}, format="json")

        response = api_client.delete(endpoint(product), {"email": "a@exemplo.com"}, format="json")

        assert response.status_code == 200
        assert not RestockAlert.objects.filter(product=product).exists()


class TestTheNoticeFires:
    def test_restocking_queues_a_notice(
        self, product: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """The transition is what matters: zero to some, not any increase.

        The task is queued `on_commit`, so it has to be captured: a test runs
        inside a transaction that is rolled back, and the callback would
        otherwise never fire — which would make this pass for the wrong reason
        if the assertion were inverted.
        """
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")

        with django_capture_on_commit_callbacks(execute=True):
            adjust_stock(product=product, quantity_delta=Decimal("10"))

        alert = RestockAlert.objects.get(product=product)
        assert alert.notified_at is not None

    def test_a_second_restock_does_not_email_again(
        self, product: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """Receiving more of something already in stock is not news."""
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")

        with django_capture_on_commit_callbacks(execute=True):
            adjust_stock(product=product, quantity_delta=Decimal("10"))

        stamped = RestockAlert.objects.get(product=product).notified_at

        with django_capture_on_commit_callbacks(execute=True):
            adjust_stock(product=product, quantity_delta=Decimal("5"))

        assert RestockAlert.objects.get(product=product).notified_at == stamped

    def test_stock_arriving_with_nobody_waiting_is_a_no_op(self, product: Any) -> None:
        empty(product)

        adjust_stock(product=product, quantity_delta=Decimal("10"))

        assert not RestockAlert.objects.exists()

    def test_resubscribing_after_a_notice_clears_the_stamp(
        self, product: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """A shopper who wants telling again next time is a new request, not a
        duplicate row."""
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")

        with django_capture_on_commit_callbacks(execute=True):
            adjust_stock(product=product, quantity_delta=Decimal("10"))

        subscribe_to_restock(product=product, email="a@exemplo.com")

        alert = RestockAlert.objects.get(product=product)
        assert alert.notified_at is None
        assert RestockAlert.objects.count() == 1


class TestDemandReport:
    def test_it_ranks_by_how_many_are_waiting(
        self, tenant: Any, product: Any, product_factory: Any
    ) -> None:
        """The merchandising value of the whole feature: what to reorder first."""
        wanted = product_factory(name="Muito procurado")
        empty(product)
        empty(wanted)

        subscribe_to_restock(product=product, email="one@exemplo.com")
        for index in range(4):
            subscribe_to_restock(product=wanted, email=f"p{index}@exemplo.com")

        rows = restock_demand(tenant.pk)

        assert rows[0]["name"] == "Muito procurado"
        assert rows[0]["waiting"] == 4
        assert rows[1]["waiting"] == 1

    def test_a_notified_request_leaves_the_report(
        self, tenant: Any, product: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """It is a list of unmet demand. Demand that was met is not on it."""
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")
        assert len(restock_demand(tenant.pk)) == 1

        with django_capture_on_commit_callbacks(execute=True):
            adjust_stock(product=product, quantity_delta=Decimal("10"))

        assert restock_demand(tenant.pk) == []


class TestTenantIsolation:
    def test_a_shop_only_sees_its_own_demand(
        self, tenant: Any, other_tenant: Any, product: Any
    ) -> None:
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")

        assert len(restock_demand(tenant.pk)) == 1
        assert restock_demand(other_tenant.pk) == []


class TestUnsubscribe:
    def test_an_unknown_address_removes_nothing(self, product: Any) -> None:
        empty(product)
        subscribe_to_restock(product=product, email="a@exemplo.com")

        removed = unsubscribe_from_restock(product=product, email="outro@exemplo.com")

        assert removed == 0
        assert RestockAlert.objects.count() == 1
