"""
The catalogue, as a spreadsheet.

A shop moving onto this platform already has its products somewhere — an Excel
sheet, an export from the old till, a list their supplier sent. Retyping four
hundred items is the reason they would give up during the trial, so the
importer is the first thing they meet.

Two rules shape everything here.

*Nothing is applied until everything validates.* A merchant importing their
catalogue on a Tuesday morning cannot be left with two hundred products in and
two hundred missing, unsure which. Rows are checked in full first, and the
write happens only if the whole sheet is clean.

*The export is the import template.* One column list serves both, so a merchant
can export what they have, edit it in Excel and send it straight back. If the
two drifted apart, that round trip — the thing they will actually do — would be
the one path nobody tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.common.spreadsheets import Column

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.tenants.models import Tenant

#: The sheet, in the order a merchant reads it: what the thing is, then what it
#: costs, then how it is sold.
PRODUCT_COLUMNS: list[Column] = [
    Column("sku", "SKU", "ARROZ-5KG", "Identificador unico. Em branco, e gerado."),
    Column("name", "Nome", "Arroz Tipo 1 5kg"),
    Column("category", "Categoria", "Mercearia", "Pelo nome. Precisa existir."),
    Column("brand", "Marca", "Marca Exemplo", "Opcional."),
    Column("unit", "Unidade", "pct", "Codigo da unidade: un, kg, pct."),
    Column("price", "Preco", "29,90"),
    Column("sale_price", "Preco promocional", "26,91", "Opcional."),
    Column("cost", "Custo", "21,00", "Opcional."),
    Column("stock", "Estoque", "30"),
    Column("status", "Situacao", "ACTIVE", "ACTIVE, DRAFT ou ARCHIVED."),
    Column("is_featured", "Destaque", "nao", "sim ou nao."),
    Column("short_description", "Descricao curta", "Grao longo, tipo 1."),
]


@dataclass
class RowError:
    line: int
    sku: str
    messages: list[str]


@dataclass
class ImportReport:
    """What an import did, or would do."""

    dry_run: bool
    total: int = 0
    created: int = 0
    updated: int = 0
    errors: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "ok": self.ok,
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "errors": [
                {"line": error.line, "sku": error.sku, "messages": error.messages}
                for error in self.errors
            ],
        }


# --- Reading values a human typed --------------------------------------------

TRUTHY = {"sim", "s", "true", "1", "yes", "y", "verdadeiro"}
FALSEY = {"nao", "n", "false", "0", "no", "falso", ""}


def _decimal(value: Any, *, field_name: str, required: bool = False) -> Decimal | None:
    """Read a number as typed on a Brazilian keyboard.

    ``1.234,56`` and ``1234.56`` mean the same amount, and a merchant will send
    whichever their spreadsheet produced. Refusing one of them would make the
    importer look broken on the shop's own data.
    """
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(str(_("%(field)s is required.")) % {"field": field_name})
        return None

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        parsed = Decimal(text)
    except InvalidOperation:
        message = str(_("%(field)s: '%(value)s' is not a number."))
        raise ValueError(message % {"field": field_name, "value": value}) from None

    if parsed < 0:
        raise ValueError(str(_("%(field)s cannot be negative.")) % {"field": field_name})
    return parsed


def _boolean(value: Any, *, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if text in TRUTHY:
        return True
    if text in FALSEY:
        return default if text == "" else False
    return default


# --- Export ------------------------------------------------------------------


def export_products(tenant: Tenant) -> list[dict[str, Any]]:
    """Every product as a row, ready to be edited and sent back."""
    from .models import Product

    products = (
        Product.objects.filter(tenant=tenant)
        .select_related("category", "brand", "sale_unit", "inventory")
        .prefetch_related("prices")
        .order_by("name")
    )

    rows = []
    for product in products:
        price = next((p for p in product.prices.all() if p.is_active), None)
        stock = getattr(product, "inventory", None)

        rows.append(
            {
                "sku": product.sku,
                "name": product.name,
                "category": product.category.name if product.category else "",
                "brand": product.brand.name if product.brand else "",
                "unit": product.sale_unit.code if product.sale_unit else "",
                "price": price.base_price if price else "",
                "sale_price": price.sale_price if price and price.sale_price else "",
                "cost": price.cost_price if price and price.cost_price else "",
                "stock": stock.quantity if stock else "",
                "status": product.status,
                "is_featured": product.is_featured,
                "short_description": product.short_description,
            }
        )

    return rows


# --- Import ------------------------------------------------------------------


def import_products(
    *,
    tenant: Tenant,
    rows: list[dict[str, Any]],
    actor: User | None = None,
    dry_run: bool = False,
    create_missing: bool = False,
) -> ImportReport:
    """Create or update products from spreadsheet rows.

    Matched on SKU, because that is the identifier the shop already uses on its
    shelves and in whatever system it is leaving. An unknown SKU is a new
    product and a known one is an update, so re-importing a corrected sheet
    fixes the catalogue rather than duplicating it.

    ``create_missing`` decides what happens to a category or brand that does
    not exist yet. It is off by default: inventing records from a typo is how a
    shop ends up with "Mercearia", "mercearia " and "Merceariaa" as three
    separate categories.
    """
    from apps.inventory.services import set_stock
    from apps.pricing.services import set_price

    from .constants import ProductStatus
    from .models import Brand, Category, Product, UnitOfMeasure
    from .services import create_product

    report = ImportReport(dry_run=dry_run, total=len(rows))

    # Resolved once rather than per row: a four-hundred-line sheet would
    # otherwise issue twelve hundred queries to look up the same few names.
    categories = {c.name.strip().lower(): c for c in Category.objects.filter(tenant=tenant)}
    brands = {b.name.strip().lower(): b for b in Brand.objects.filter(tenant=tenant)}
    units = {u.code.strip().lower(): u for u in UnitOfMeasure.objects.filter(tenant=tenant)}
    existing = {p.sku.strip().lower(): p for p in Product.objects.filter(tenant=tenant)}

    statuses = {choice.value for choice in ProductStatus}
    prepared: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=2):  # line 1 is the header
        messages: list[str] = []
        sku = str(row.get("sku") or "").strip()
        name = str(row.get("name") or "").strip()

        if not name:
            messages.append(str(_("Name is required.")))

        category_name = str(row.get("category") or "").strip()
        category = categories.get(category_name.lower())
        if not category_name:
            messages.append(str(_("Category is required.")))
        elif category is None and not create_missing:
            messages.append(str(_("Unknown category: %(name)s")) % {"name": category_name})

        unit_code = str(row.get("unit") or "").strip()
        unit = units.get(unit_code.lower())
        if not unit_code:
            messages.append(str(_("Unit is required.")))
        elif unit is None:
            messages.append(str(_("Unknown unit: %(code)s")) % {"code": unit_code})

        brand_name = str(row.get("brand") or "").strip()
        brand = brands.get(brand_name.lower())
        if brand_name and brand is None and not create_missing:
            messages.append(str(_("Unknown brand: %(name)s")) % {"name": brand_name})

        status = str(row.get("status") or ProductStatus.ACTIVE).strip().upper()
        if status not in statuses:
            messages.append(str(_("Unknown status: %(status)s")) % {"status": status})

        values: dict[str, Any] = {}
        numeric = (("price", True), ("sale_price", False), ("cost", False), ("stock", False))
        for key, required in numeric:
            try:
                values[key] = _decimal(row.get(key), field_name=key, required=required)
            except ValueError as exc:
                messages.append(str(exc))

        if messages:
            report.errors.append(RowError(line=index, sku=sku or name, messages=messages))
            continue

        prepared.append(
            {
                "line": index,
                "sku": sku,
                "name": name,
                "category_name": category_name,
                "category": category,
                "brand_name": brand_name,
                "brand": brand,
                "unit": unit,
                "status": status,
                "is_featured": _boolean(row.get("is_featured")),
                "short_description": str(row.get("short_description") or "").strip()[:255],
                **values,
            }
        )

    # Nothing is written while anything is wrong. A half-imported catalogue is
    # worse than none, because the merchant cannot tell which half arrived.
    if report.errors or dry_run:
        for item in prepared:
            if item["sku"].lower() in existing:
                report.updated += 1
            else:
                report.created += 1
        return report

    with transaction.atomic():
        for item in prepared:
            category = item["category"] or _ensure(
                Category, tenant=tenant, name=item["category_name"], cache=categories
            )
            brand = item["brand"] or _ensure(
                Brand, tenant=tenant, name=item["brand_name"], cache=brands
            )

            product = existing.get(item["sku"].lower())

            if product is None:
                product = create_product(
                    tenant=tenant,
                    name=item["name"],
                    category=category,
                    sale_unit=item["unit"],
                    sku=item["sku"],
                    actor=actor,
                    status=item["status"],
                    is_featured=item["is_featured"],
                    short_description=item["short_description"],
                    brand=brand,
                )
                existing[product.sku.lower()] = product
                report.created += 1
            else:
                product.name = item["name"]
                product.category = category
                product.brand = brand
                product.sale_unit = item["unit"]
                product.status = item["status"]
                product.is_featured = item["is_featured"]
                product.short_description = item["short_description"]
                product.save()
                report.updated += 1

            if item["price"] is not None:
                set_price(
                    tenant=tenant,
                    product=product,
                    base_price=item["price"],
                    sale_price=item["sale_price"],
                    cost_price=item["cost"],
                    actor=actor,
                )

            if item["stock"] is not None:
                set_stock(
                    product=product,
                    quantity=item["stock"],
                    actor=actor,
                    note=str(_("Spreadsheet import")),
                )

    return report


def _ensure(model: Any, *, tenant: Tenant, name: str, cache: dict[str, Any]) -> Any:
    """Fetch or create a category/brand by name, remembering it for later rows.

    Only reached when the caller asked for missing records to be created; the
    validation pass has already refused the row otherwise.
    """
    if not name:
        return None

    from .services import unique_slug

    record, _created = model.objects.get_or_create(
        tenant=tenant,
        name=name,
        defaults={"slug": unique_slug(model, tenant.pk, name)},
    )
    cache[name.lower()] = record
    return record
