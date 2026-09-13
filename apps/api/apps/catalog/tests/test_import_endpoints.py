"""
The import and export endpoints.

The module beneath these is tested separately; what matters here is the part a
merchant touches — that a download arrives as a file their spreadsheet opens,
that a bad file is refused with something they can act on, and that a sheet
with mistakes in it comes back as a readable report rather than an error page.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest

from apps.catalog.importexport import PRODUCT_COLUMNS
from apps.catalog.models import Product
from apps.common.spreadsheets import CSV, XLSX, render

pytestmark = pytest.mark.django_db

EXPORT = "/api/v1/admin/products/export/"
TEMPLATE = "/api/v1/admin/products/import-template/"
IMPORT = "/api/v1/admin/products/import/"


def sheet(rows: list[dict[str, Any]], fmt: str = CSV) -> BytesIO:
    """An uploadable file, built the same way the export builds one."""
    blob = render(columns=PRODUCT_COLUMNS, rows=rows, fmt=fmt)
    upload = BytesIO(blob)
    upload.name = f"produtos.{fmt}"
    return upload


def valid_row(**overrides: Any) -> dict[str, Any]:
    return {
        "sku": "IMPORTADO-1",
        "name": "Produto Importado",
        "category": "Mercearia",
        "unit": "un",
        "price": "12,50",
        "stock": "5",
        "status": "ACTIVE",
        **overrides,
    }


@pytest.fixture
def catalogue(tenant: Any, category: Any, unit: Any) -> None:
    category.name = "Mercearia"
    category.save(update_fields=["name"])
    unit.code = "un"
    unit.save(update_fields=["code"])


class TestExport:
    @pytest.mark.parametrize(
        ("fmt", "content_type"),
        [
            (CSV, "text/csv"),
            (XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ],
    )
    def test_it_downloads_as_a_file(
        self, admin_client_api: Any, product: Any, fmt: str, content_type: str
    ) -> None:
        response = admin_client_api.get(f"{EXPORT}?fmt={fmt}")

        assert response.status_code == 200
        assert content_type in response["Content-Type"]
        assert "attachment" in response["Content-Disposition"]
        assert f".{fmt}" in response["Content-Disposition"]

    def test_the_download_name_reaches_the_browser(
        self, admin_client_api: Any, product: Any
    ) -> None:
        """The storefront and the API are on different origins, so without this
        header the browser saves the file under the URL's last segment."""
        response = admin_client_api.get(EXPORT)

        assert "Content-Disposition" in response["Access-Control-Expose-Headers"]

    def test_an_unknown_format_falls_back_rather_than_failing(
        self, admin_client_api: Any, product: Any
    ) -> None:
        response = admin_client_api.get(f"{EXPORT}?fmt=pdf")

        assert response.status_code == 200
        assert ".xlsx" in response["Content-Disposition"]

    def test_the_export_contains_the_products(self, admin_client_api: Any, product: Any) -> None:
        body = admin_client_api.get(f"{EXPORT}?fmt=csv").content.decode("utf-8-sig")

        assert product.sku in body
        assert product.name in body


class TestTemplate:
    def test_it_carries_the_headings_and_an_example(self, admin_client_api: Any) -> None:
        """A merchant needs to see what goes in each column before filling in
        four hundred rows, not after."""
        body = admin_client_api.get(f"{TEMPLATE}?fmt=csv").content.decode("utf-8-sig")
        lines = body.splitlines()

        assert lines[0].split(";") == [column.header for column in PRODUCT_COLUMNS]
        assert "ARROZ-5KG" in lines[1]


class TestImport:
    def test_a_good_sheet_creates_the_products(
        self, admin_client_api: Any, catalogue: None, tenant: Any
    ) -> None:
        response = admin_client_api.post(IMPORT, {"file": sheet([valid_row()])}, format="multipart")

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["created"] == 1
        assert Product.objects.filter(tenant=tenant, sku="IMPORTADO-1").exists()

    def test_an_xlsx_upload_works_too(
        self, admin_client_api: Any, catalogue: None, tenant: Any
    ) -> None:
        """Excel is what the shops actually have."""
        response = admin_client_api.post(
            IMPORT, {"file": sheet([valid_row()], fmt=XLSX)}, format="multipart"
        )

        assert response.status_code == 200
        assert response.json()["created"] == 1

    def test_a_sheet_with_errors_answers_200_with_a_report(
        self, admin_client_api: Any, catalogue: None, tenant: Any
    ) -> None:
        """Three bad lines out of four hundred is a result to read, not a failed
        request. An error status would leave the client with nothing to show."""
        response = admin_client_api.post(
            IMPORT,
            {"file": sheet([valid_row(), valid_row(sku="BAD", price="caro")])},
            format="multipart",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["errors"][0]["sku"] == "BAD"
        # Nothing was written, including the row that was fine.
        assert not Product.objects.filter(tenant=tenant, sku="IMPORTADO-1").exists()

    def test_a_dry_run_previews_without_writing(
        self, admin_client_api: Any, catalogue: None, tenant: Any
    ) -> None:
        response = admin_client_api.post(
            IMPORT, {"file": sheet([valid_row()]), "dry_run": "true"}, format="multipart"
        )

        assert response.json() == {
            "dry_run": True,
            "ok": True,
            "total": 1,
            "created": 1,
            "updated": 0,
            "errors": [],
        }
        assert not Product.objects.filter(tenant=tenant, sku="IMPORTADO-1").exists()

    def test_no_file_is_refused_clearly(self, admin_client_api: Any) -> None:
        response = admin_client_api.post(IMPORT, {}, format="multipart")

        assert response.status_code == 400

    def test_a_file_with_only_headings_is_refused(
        self, admin_client_api: Any, catalogue: None
    ) -> None:
        """Otherwise "imported 0 products" reads as success to someone who
        picked the wrong file."""
        response = admin_client_api.post(IMPORT, {"file": sheet([])}, format="multipart")

        assert response.status_code == 400

    def test_staff_without_permission_cannot_import(
        self, staff_client: Any, catalogue: None
    ) -> None:
        response = staff_client.post(IMPORT, {"file": sheet([valid_row()])}, format="multipart")

        assert response.status_code == 403
