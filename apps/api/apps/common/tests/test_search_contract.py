"""
`?search=` has to actually search.

Seven of the eight admin tables shipped a search box that did nothing. DRF only
reads `search_fields` through `SearchFilter`, and `SearchFilter` was not in
`DEFAULT_FILTER_BACKENDS` — so three viewsets declared the attribute and
filtered nothing, and four never declared it at all. The request succeeded, the
full unfiltered page came back, and the table redrew with the same rows. There
is no error to notice: searching for "Arroz" simply returned the alphabetical
top of the list.

Nothing could catch it. The attribute is valid on any viewset whether or not
the backend that reads it is installed, and the endpoint answers 200 either way.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.urls import get_resolver, resolve
from rest_framework.filters import SearchFilter

pytestmark = pytest.mark.django_db


def _routed_viewsets() -> dict[str, Any]:
    """Every viewset class reachable through the URL conf."""
    found: dict[str, Any] = {}

    def walk(patterns: Any) -> None:
        for entry in patterns:
            if hasattr(entry, "url_patterns"):
                walk(entry.url_patterns)
                continue
            cls = getattr(entry.callback, "cls", None)
            if cls is not None:
                found[cls.__name__] = cls

    walk(get_resolver().url_patterns)
    return found


class TestWiring:
    def test_search_backend_is_installed(self) -> None:
        """The one line whose absence made every `search_fields` decorative."""
        from rest_framework.settings import api_settings

        assert SearchFilter in api_settings.DEFAULT_FILTER_BACKENDS

    def test_declared_search_fields_are_reachable(self) -> None:
        """A viewset that declares `search_fields` must resolve a backend for them.

        Generic on purpose: this holds for viewsets not written yet, including
        one that overrides `filter_backends` locally and drops SearchFilter
        while keeping the fields.
        """
        offenders = [
            name
            for name, cls in _routed_viewsets().items()
            if getattr(cls, "search_fields", None)
            and not any(issubclass(backend, SearchFilter) for backend in cls.filter_backends)
        ]

        assert offenders == [], f"search_fields declared but never read: {offenders}"


class TestAdminTables:
    """The admin tables that render a search box, and so must answer one.

    Kept as a list of paths rather than derived, because the contract being
    protected is between two repositories: `MuraDataTable`'s `searchable` prop
    sends `?search=`, and these are the endpoints it sends it to.
    """

    SEARCHABLE = [
        "/api/v1/admin/customers/",
        "/api/v1/admin/finance/transactions/",
        "/api/v1/admin/inventory/",
        "/api/v1/admin/orders/",
        "/api/v1/admin/products/",
        "/api/v1/admin/stock-batches/",
        "/api/v1/admin/users/",
    ]

    def test_every_searchable_endpoint_declares_fields(self) -> None:
        missing = [
            path
            for path in self.SEARCHABLE
            if not getattr(resolve(path).func.cls, "search_fields", None)
        ]

        assert missing == [], f"Tables with a search box the API ignores: {missing}"


class TestSearchNarrowsResults:
    """The behaviour itself, on the endpoint the bug was found on."""

    def test_inventory_search_filters_by_product_name(
        self, admin_client_api: Any, product_factory: Any
    ) -> None:
        product_factory(name="Arroz Branco 5kg")
        product_factory(name="Feijao Carioca 1kg")

        response = admin_client_api.get("/api/v1/admin/inventory/?search=Arroz")

        assert response.status_code == 200
        names = [row["product_name"] for row in response.json()["results"]]
        assert names == ["Arroz Branco 5kg"], names

    def test_search_that_matches_nothing_returns_nothing(
        self, admin_client_api: Any, product_factory: Any
    ) -> None:
        """Guards the assertion above: an unfiltered list would still contain a
        row here, which is exactly how the bug looked in the browser."""
        product_factory(name="Arroz Branco 5kg")

        response = admin_client_api.get("/api/v1/admin/inventory/?search=zzzznotathing")

        assert response.status_code == 200
        assert response.json()["results"] == []
