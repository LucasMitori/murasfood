"""
Catalog models.

Two decisions worth calling out:

*Prices do not live on ``Product``.* A product's price changes over time, varies
by promotion and must keep a history — that is a domain of its own
(:mod:`apps.pricing`). Storing a ``price`` column here would invite exactly the
denormalised, unauditable field spec §9 warns against.

*Units are first-class.* A bakery item sold per 100 g and a sack of rice sold by
the package cannot share a hard-coded "quantity is an integer" assumption
(spec §8, §91).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TenantQuerySet

from .constants import BarcodeType, ProductStatus, ProductType, UnitKind


class UnitOfMeasure(TenantOwnedModel):
    """How a product's quantity is expressed and stepped in the UI."""

    code = models.CharField(_("code"), max_length=12)
    name = models.CharField(_("name"), max_length=60)
    kind = models.CharField(
        _("kind"), max_length=12, choices=UnitKind.choices, default=UnitKind.UNIT
    )
    precision = models.PositiveSmallIntegerField(
        _("decimal places"),
        default=0,
        help_text=_("0 for countable units, 3 for weight."),
    )
    step = models.DecimalField(
        _("quantity step"),
        max_digits=10,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=_("Increment used by quantity controls, e.g. 0.1 kg."),
    )

    class Meta:
        verbose_name = _("unit of measure")
        verbose_name_plural = _("units of measure")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_unit_tenant_code"),
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def is_fractional(self) -> bool:
        return self.precision > 0


class Brand(TenantOwnedModel):
    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140)
    description = models.TextField(_("description"), blank=True)
    logo = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="brand_logos",
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_brand_tenant_slug"),
        ]

    def __str__(self) -> str:
        return self.name


class Category(TenantOwnedModel):
    """A catalog section. Self-referencing to allow one or two levels of nesting."""

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent category"),
    )
    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140)
    description = models.TextField(_("description"), blank=True)
    image = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="category_images",
    )
    position = models.IntegerField(_("position"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    is_featured = models.BooleanField(_("featured"), default=False)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_category_tenant_slug"),
        ]
        indexes = [models.Index(fields=["tenant", "is_active", "position"])]

    def __str__(self) -> str:
        return self.name

    def ancestors(self) -> list[Category]:
        """Breadcrumb trail, root first.

        Bounded by a depth guard so a cycle introduced by a bad import cannot
        hang a request.
        """
        trail: list[Category] = []
        node = self.parent
        depth = 0
        while node is not None and depth < 10:
            trail.insert(0, node)
            node = node.parent
            depth += 1
        return trail


class CategoryTranslation(TenantOwnedModel):
    """Localised category copy.

    User-facing strings are never hard-coded in business logic (spec §58); this
    is where a merchant provides ``en`` or ``es`` names for a pt-BR catalog.
    """

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="translations", verbose_name=_("category")
    )
    locale = models.CharField(_("locale"), max_length=10)
    name = models.CharField(_("name"), max_length=120)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("category translation")
        verbose_name_plural = _("category translations")
        constraints = [
            models.UniqueConstraint(
                fields=["category", "locale"], name="uniq_category_translation_locale"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.category} [{self.locale}]"


class ProductTag(TenantOwnedModel):
    """Free-form label: "organic", "gluten free", "local producer"."""

    name = models.CharField(_("name"), max_length=60)
    slug = models.SlugField(_("slug"), max_length=80)
    color = models.CharField(_("colour"), max_length=7, blank=True)

    class Meta:
        verbose_name = _("product tag")
        verbose_name_plural = _("product tags")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_tag_tenant_slug"),
        ]

    def __str__(self) -> str:
        return self.name


class ProductQuerySet(TenantQuerySet):
    """Query helpers that encode the storefront's visibility rules.

    Extends ``TenantQuerySet`` so ``for_tenant()`` stays available: a custom
    manager that quietly drops tenant scoping would be a data-leak waiting to
    happen.
    """

    def purchasable(self) -> ProductQuerySet:
        """Products a customer may see and add to a cart.

        Note that ``OUT_OF_STOCK`` products stay visible: temporarily running
        out is not a reason to hide an item from the catalog (spec §92).
        """
        return self.filter(
            is_active=True, status__in=[ProductStatus.ACTIVE, ProductStatus.OUT_OF_STOCK]
        )

    def with_relations(self) -> ProductQuerySet:
        """Prefetch everything a product card needs, avoiding N+1 queries."""
        return self.select_related("category", "brand", "sale_unit").prefetch_related(
            "images__asset", "tags", "barcodes"
        )


class Product(TenantOwnedModel):
    """A sellable item."""

    sku = models.CharField(_("SKU"), max_length=64)
    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(_("slug"), max_length=280)
    short_description = models.CharField(_("short description"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("category"),
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("brand"),
    )
    tags = models.ManyToManyField(ProductTag, related_name="products", blank=True)

    product_type = models.CharField(
        _("type"), max_length=16, choices=ProductType.choices, default=ProductType.SIMPLE
    )
    sale_unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("sale unit"),
    )
    unit_quantity = models.DecimalField(
        _("package size"),
        max_digits=10,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text=_("Content per sold item, e.g. 1.000 for a 1 kg pack."),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=ProductStatus.choices, default=ProductStatus.DRAFT
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_featured = models.BooleanField(_("featured"), default=False)

    requires_weighing = models.BooleanField(
        _("weighed at pickup"),
        default=False,
        help_text=_("Final price depends on the weight measured when preparing the order."),
    )
    requires_age_check = models.BooleanField(_("age restricted"), default=False)
    tax_category = models.CharField(_("tax category"), max_length=32, blank=True)

    max_quantity_per_order = models.DecimalField(
        _("max quantity per order"),
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )

    # Denormalised counters. They are derived data used only for sorting and
    # merchandising — never for money, and always recomputed from orders.
    sales_count = models.PositiveIntegerField(_("units sold"), default=0)
    view_count = models.PositiveIntegerField(_("views"), default=0)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="uniq_product_tenant_sku"),
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_product_tenant_slug"),
            models.CheckConstraint(
                condition=models.Q(unit_quantity__gt=0), name="product_unit_quantity_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "is_active"]),
            models.Index(fields=["tenant", "category", "is_active"]),
            models.Index(fields=["tenant", "is_featured", "is_active"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "-sales_count"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_purchasable(self) -> bool:
        return self.is_active and self.status in {ProductStatus.ACTIVE, ProductStatus.OUT_OF_STOCK}

    @property
    def sells_fractional_quantity(self) -> bool:
        """Whether a customer may order 1.350 of this item."""
        return self.product_type == ProductType.WEIGHTED or self.sale_unit.is_fractional

    @property
    def primary_image(self) -> ProductImage | None:
        images = list(self.images.all())
        if not images:
            return None
        return next((img for img in images if img.is_primary), images[0])


class ProductTranslation(TenantOwnedModel):
    """Localised product copy."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="translations", verbose_name=_("product")
    )
    locale = models.CharField(_("locale"), max_length=10)
    name = models.CharField(_("name"), max_length=255)
    short_description = models.CharField(_("short description"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("product translation")
        verbose_name_plural = _("product translations")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "locale"], name="uniq_product_translation_locale"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.product} [{self.locale}]"


class ProductImage(TenantOwnedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images", verbose_name=_("product")
    )
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.PROTECT,
        related_name="product_images",
        verbose_name=_("image"),
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    caption = models.CharField(
        _("caption"),
        max_length=160,
        blank=True,
        help_text=_(
            "Shown under the photo in the gallery. Describes this shot — "
            '"rótulo", "porção servida" — rather than repeating the product name.'
        ),
    )
    is_primary = models.BooleanField(_("primary"), default=False)

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_image_per_product",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.product} #{self.position}"


class ProductBarcode(TenantOwnedModel):
    """Scannable code. Unique per tenant so a scan resolves to one product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="barcodes", verbose_name=_("product")
    )
    code = models.CharField(_("code"), max_length=64, db_index=True)
    barcode_type = models.CharField(
        _("type"), max_length=12, choices=BarcodeType.choices, default=BarcodeType.EAN13
    )
    is_primary = models.BooleanField(_("primary"), default=False)

    class Meta:
        verbose_name = _("barcode")
        verbose_name_plural = _("barcodes")
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_barcode_tenant_code"),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.code


class Favorite(TenantOwnedModel):
    """A customer's saved product (spec §22)."""

    customer = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="favorites"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")

    class Meta:
        verbose_name = _("favourite")
        verbose_name_plural = _("favourites")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product"], name="uniq_favorite_customer_product"
            ),
        ]
        indexes = [models.Index(fields=["customer", "-created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.customer} ♥ {self.product}"
