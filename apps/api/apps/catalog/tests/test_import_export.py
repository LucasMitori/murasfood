"""
Importing a shop's catalogue from a spreadsheet.

This is the first thing a new merchant does and the easiest place to lose their
trust: it writes their entire product list in one go, from a file they made in
Excel. The properties worth protecting are that a partial import can never
happen, that re-importing corrects rather than duplicates, and that the file
this system exports is a file it can read back.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.catalog.importexport import (
    PRODUCT_COLUMNS,
    export_products,
    import_products,
)
from apps.catalog.models import Category, Product
from apps.common.spreadsheets import CSV, XLSX, parse, render

pytestmark = pytest.mark.django_db


def row(**overrides: Any) -> dict[str, Any]:
    """A valid line, adjusted per test."""
    return {
        "sku": "ARROZ-5KG",
        "name": "Arroz Tipo 1 5kg",
        "category": "Mercearia",
        "brand": "",
        "unit": "un",
        "price": "29,90",
        "sale_price": "",
        "cost": "21,00",
        "stock": "30",
        "status": "ACTIVE",
        "is_featured": "nao",
        "short_description": "",
        **overrides,
    }


@pytest.fixture
def catalogue(tenant: Any, category: Any, unit: Any) -> dict[str, Any]:
    """Names the importer resolves against, matching the default row above."""
    category.name = "Mercearia"
    category.save(update_fields=["name"])
    unit.code = "un"
    unit.save(update_fields=["code"])
    return {"category": category, "unit": unit}


class TestCreatingAndUpdating:
    def test_a_new_sku_creates_a_product_with_price_and_stock(
        self, tenant: Any, catalogue: Any
    ) -> None:
        report = import_products(tenant=tenant, rows=[row()])

        assert report.ok, report.errors
        assert (report.created, report.updated) == (1, 0)

        product = Product.objects.get(tenant=tenant, sku="ARROZ-5KG")
        assert product.name == "Arroz Tipo 1 5kg"
        assert product.prices.filter(is_active=True).first().base_price == Decimal("29.90")
        assert product.inventory.quantity == Decimal("30.000")

    def test_a_known_sku_updates_rather_than_duplicating(self, tenant: Any, catalogue: Any) -> None:
        """Re-importing a corrected sheet is the normal way to fix a mistake."""
        import_products(tenant=tenant, rows=[row()])
        report = import_products(
            tenant=tenant, rows=[row(name="Arroz Tipo 1 5kg (novo)", price="31,50")]
        )

        assert (report.created, report.updated) == (0, 1)
        assert Product.objects.filter(tenant=tenant, sku="ARROZ-5KG").count() == 1

        product = Product.objects.get(tenant=tenant, sku="ARROZ-5KG")
        assert product.name == "Arroz Tipo 1 5kg (novo)"
        assert product.prices.filter(is_active=True).first().base_price == Decimal("31.50")

    def test_prices_may_be_written_either_way_round(self, tenant: Any, catalogue: Any) -> None:
        """A Brazilian spreadsheet writes 1.234,56 and an English one 1234.56."""
        import_products(
            tenant=tenant,
            rows=[
                row(sku="A", price="1.234,56"),
                row(sku="B", price="1234.56"),
            ],
        )

        prices = {
            product.sku: product.prices.filter(is_active=True).first().base_price
            for product in Product.objects.filter(tenant=tenant, sku__in=["A", "B"])
        }
        assert prices == {"A": Decimal("1234.56"), "B": Decimal("1234.56")}


class TestNothingIsAppliedUntilEverythingValidates:
    def test_one_bad_row_writes_nothing_at_all(self, tenant: Any, catalogue: Any) -> None:
        """The property that makes an import safe to attempt.

        Left half-applied, a merchant cannot tell which products arrived and
        which did not, and their only recovery is to inspect four hundred rows
        by hand.
        """
        report = import_products(
            tenant=tenant,
            rows=[
                row(sku="GOOD-1"),
                row(sku="BAD-1", price="muito caro"),
                row(sku="GOOD-2"),
            ],
        )

        assert not report.ok
        assert Product.objects.filter(tenant=tenant, sku__startswith="GOOD").count() == 0

    def test_the_error_names_the_line_and_the_reason(self, tenant: Any, catalogue: Any) -> None:
        """A merchant has to be able to find the row in their own file."""
        report = import_products(tenant=tenant, rows=[row(), row(sku="BAD", price="")])

        assert len(report.errors) == 1
        error = report.errors[0]
        # Line 1 is the header, so the second data row is line 3.
        assert error.line == 3
        assert error.sku == "BAD"
        assert any("price" in message for message in error.messages)

    def test_a_dry_run_reports_but_writes_nothing(self, tenant: Any, catalogue: Any) -> None:
        report = import_products(tenant=tenant, rows=[row()], dry_run=True)

        assert report.ok
        assert report.created == 1
        assert not Product.objects.filter(tenant=tenant, sku="ARROZ-5KG").exists()


class TestUnknownNames:
    def test_an_unknown_category_is_refused_by_default(self, tenant: Any, catalogue: Any) -> None:
        """Silently creating one is how a typo becomes a second category."""
        report = import_products(tenant=tenant, rows=[row(category="Padaria Nova")])

        assert not report.ok
        assert "Padaria Nova" in report.errors[0].messages[0]

    def test_create_missing_makes_the_category(self, tenant: Any, catalogue: Any) -> None:
        report = import_products(
            tenant=tenant, rows=[row(category="Padaria Nova")], create_missing=True
        )

        assert report.ok, report.errors
        assert Category.objects.filter(tenant=tenant, name="Padaria Nova").exists()

    def test_an_unknown_unit_is_always_refused(self, tenant: Any, catalogue: Any) -> None:
        """Units are a fixed vocabulary with a precision each — inventing "cx"
        would mean guessing whether it is divisible."""
        report = import_products(tenant=tenant, rows=[row(unit="caixa")], create_missing=True)

        assert not report.ok
        assert "caixa" in report.errors[0].messages[0]


class TestTheRoundTrip:
    """What is exported must be importable, in both formats.

    This is the path a merchant actually takes — export, edit in Excel, import
    — so it is the one that must not break when a column is added.
    """

    @pytest.mark.parametrize("fmt", [CSV, XLSX])
    def test_export_then_import_leaves_the_catalogue_unchanged(
        self, tenant: Any, catalogue: Any, fmt: str
    ) -> None:
        import_products(tenant=tenant, rows=[row(sku="A"), row(sku="B", name="Feijao Carioca")])
        before = export_products(tenant)

        blob = render(columns=PRODUCT_COLUMNS, rows=before, fmt=fmt)
        parsed = parse(content=blob, filename=f"catalogo.{fmt}", columns=PRODUCT_COLUMNS)

        report = import_products(tenant=tenant, rows=parsed)

        assert report.ok, report.errors
        # Everything matched an existing SKU: a round trip is an update, never a
        # second copy of the shop's own catalogue.
        assert (report.created, report.updated) == (0, 2)
        assert export_products(tenant) == before

    def test_the_exported_header_is_what_the_importer_reads(self) -> None:
        """The two share one column list, so this holds by construction — but it
        is the assumption the round trip rests on, so it is worth stating."""
        blob = render(columns=PRODUCT_COLUMNS, rows=[], fmt=CSV)
        header = blob.decode("utf-8-sig").splitlines()[0].split(";")

        assert header == [column.header for column in PRODUCT_COLUMNS]
