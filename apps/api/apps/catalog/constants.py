"""Catalog enumerations."""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    ACTIVE = "ACTIVE", _("Active")
    INACTIVE = "INACTIVE", _("Inactive")
    OUT_OF_STOCK = "OUT_OF_STOCK", _("Out of stock")
    ARCHIVED = "ARCHIVED", _("Archived")


class ProductType(models.TextChoices):
    """How a product is sold, which drives quantity handling at checkout."""

    SIMPLE = "SIMPLE", _("Sold by unit")
    WEIGHTED = "WEIGHTED", _("Sold by weight")
    BUNDLE = "BUNDLE", _("Bundle")


class UnitKind(models.TextChoices):
    UNIT = "UNIT", _("Unit")
    WEIGHT = "WEIGHT", _("Weight")
    VOLUME = "VOLUME", _("Volume")
    LENGTH = "LENGTH", _("Length")


class BarcodeType(models.TextChoices):
    EAN13 = "EAN13", _("EAN-13")
    EAN8 = "EAN8", _("EAN-8")
    UPC = "UPC", _("UPC")
    INTERNAL = "INTERNAL", _("Internal")


#: Units seeded for every new tenant. A bakery sells by the piece *and* by the
#: 100 g; produce sells by the kilo; drinks by the litre. Forcing everything
#: into "unit" is exactly the modelling mistake spec §8 warns about.
DEFAULT_UNITS: tuple[dict[str, object], ...] = (
    {"code": "un", "name": "Unit", "kind": UnitKind.UNIT, "precision": 0, "step": Decimal("1")},
    {
        "code": "kg",
        "name": "Kilogram",
        "kind": UnitKind.WEIGHT,
        "precision": 3,
        "step": Decimal("0.1"),
    },
    {"code": "g", "name": "Gram", "kind": UnitKind.WEIGHT, "precision": 0, "step": Decimal("100")},
    {"code": "l", "name": "Litre", "kind": UnitKind.VOLUME, "precision": 3, "step": Decimal("0.5")},
    {
        "code": "ml",
        "name": "Millilitre",
        "kind": UnitKind.VOLUME,
        "precision": 0,
        "step": Decimal("100"),
    },
    {"code": "pct", "name": "Package", "kind": UnitKind.UNIT, "precision": 0, "step": Decimal("1")},
    {"code": "cx", "name": "Box", "kind": UnitKind.UNIT, "precision": 0, "step": Decimal("1")},
    {"code": "grf", "name": "Bottle", "kind": UnitKind.UNIT, "precision": 0, "step": Decimal("1")},
    {"code": "pc", "name": "Piece", "kind": UnitKind.UNIT, "precision": 0, "step": Decimal("1")},
)


#: Sort options exposed on the storefront, mapped to safe ORM expressions.
#: A user-supplied ``ordering`` value is never passed to the ORM directly.
PRODUCT_SORT_OPTIONS: dict[str, tuple[str, ...]] = {
    "relevance": ("-is_featured", "name"),
    "name": ("name",),
    "-name": ("-name",),
    "price": ("effective_price", "name"),
    "-price": ("-effective_price", "name"),
    "newest": ("-created_at",),
    "best_sellers": ("-sales_count", "name"),
}
