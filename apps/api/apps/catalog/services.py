"""Catalog business operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Model
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.audit.services import record_audit
from apps.common.exceptions import ConflictError, DomainError

from .constants import DEFAULT_UNITS, ProductStatus
from .models import (
    Category,
    Favorite,
    Product,
    ProductImage,
    UnitOfMeasure,
)

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.catalog")


class ProductNotPurchasableError(DomainError):
    default_detail = _("This product is not available for purchase.")
    default_code = "PRODUCT_NOT_PURCHASABLE"


def unique_slug(model: type[Model], tenant_id: Any, value: str, *, exclude_pk: Any = None) -> str:
    """Generate a slug unique within a tenant.

    Slugs are unique *per tenant*, so two merchants may both sell "pao-frances".
    """
    base = slugify(value)[:200].strip("-") or "item"
    candidate = base
    suffix = 2
    while True:
        queryset = model.objects.filter(tenant_id=tenant_id, slug=candidate)
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)
        if not queryset.exists():
            return candidate
        candidate = f"{base[:195]}-{suffix}"
        suffix += 1


def ensure_default_units(tenant: Tenant) -> dict[str, UnitOfMeasure]:
    """Create the standard units for a tenant. Idempotent."""
    units: dict[str, UnitOfMeasure] = {}
    for spec in DEFAULT_UNITS:
        unit, _created = UnitOfMeasure.objects.get_or_create(
            tenant=tenant,
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "kind": spec["kind"],
                "precision": spec["precision"],
                "step": spec["step"],
            },
        )
        units[unit.code] = unit
    return units


@transaction.atomic
def create_product(
    *,
    tenant: Tenant,
    name: str,
    category: Category,
    sale_unit: UnitOfMeasure,
    sku: str = "",
    actor: User | None = None,
    **fields: Any,
) -> Product:
    """Create a product in ``DRAFT`` and give it an inventory record.

    New products start as drafts so a half-configured item — no price, no photo —
    cannot appear on the storefront.
    """
    from apps.inventory.services import get_or_create_item

    slug = fields.pop("slug", None) or unique_slug(Product, tenant.pk, name)
    generated_sku = sku.strip() or slug.upper().replace("-", "")[:32]

    if Product.objects.filter(tenant=tenant, sku=generated_sku).exists():
        raise ConflictError(
            _("A product with this SKU already exists."),
            code="DUPLICATE_SKU",
            details={"sku": generated_sku},
        )

    product = Product.objects.create(
        tenant=tenant,
        name=name,
        slug=slug,
        sku=generated_sku,
        category=category,
        sale_unit=sale_unit,
        status=fields.pop("status", ProductStatus.DRAFT),
        **fields,
    )
    get_or_create_item(product)

    record_audit(
        action="catalog.product_created",
        tenant=tenant,
        actor=actor,
        resource=product,
        new_values={"name": name, "sku": generated_sku},
    )
    return product


@transaction.atomic
def publish_product(product: Product, *, actor: User | None = None) -> Product:
    """Move a product to ``ACTIVE`` after checking it is actually sellable.

    Refusing to publish an unpriced product is cheaper than discovering the
    problem when a customer cannot check out.
    """
    from apps.pricing.selectors import resolve_price

    if resolve_price(product) is None:
        raise DomainError(
            _("Set a price before publishing this product."),
            code="PRODUCT_WITHOUT_PRICE",
        )

    previous = product.status
    product.status = ProductStatus.ACTIVE
    product.is_active = True
    product.save(update_fields=["status", "is_active", "updated_at"])

    record_audit(
        action="catalog.product_published",
        tenant=product.tenant,
        actor=actor,
        resource=product,
        old_values={"status": previous},
        new_values={"status": product.status},
    )
    return product


@transaction.atomic
def archive_product(product: Product, *, actor: User | None = None) -> Product:
    """Archive rather than delete.

    Order history references products; deleting one would break past orders and
    every report derived from them.
    """
    previous = product.status
    product.status = ProductStatus.ARCHIVED
    product.is_active = False
    product.save(update_fields=["status", "is_active", "updated_at"])

    record_audit(
        action="catalog.product_archived",
        tenant=product.tenant,
        actor=actor,
        resource=product,
        old_values={"status": previous},
        new_values={"status": product.status},
    )
    return product


@transaction.atomic
def attach_image(
    *, product: Product, asset_id: Any, position: int = 0, is_primary: bool = False
) -> ProductImage:
    """Attach an uploaded asset to a product.

    Promoting a new primary demotes the old one first: the unique constraint
    allows only one primary image per product.
    """
    from apps.media.models import MediaAsset

    asset = MediaAsset.objects.filter(pk=asset_id, tenant_id=product.tenant_id).first()
    if asset is None:
        raise DomainError(_("Image not found."), code="MEDIA_NOT_FOUND")

    make_primary = is_primary or not product.images.exists()
    if make_primary:
        ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)

    return ProductImage.objects.create(
        tenant_id=product.tenant_id,
        product=product,
        asset=asset,
        position=position,
        is_primary=make_primary,
    )


@transaction.atomic
def reorder_images(product: Product, ordered_ids: list[Any]) -> None:
    """Persist a drag-and-drop reordering. The first image becomes primary."""
    images = {str(img.pk): img for img in product.images.all()}
    for index, image_id in enumerate(ordered_ids):
        image = images.get(str(image_id))
        if image is None:
            continue
        image.position = index
        image.is_primary = index == 0
        image.save(update_fields=["position", "is_primary", "updated_at"])


def toggle_favorite(*, customer: User, product: Product) -> tuple[Favorite | None, bool]:
    """Add or remove a favourite.

    Returns ``(favorite, created)``; ``favorite`` is ``None`` when the product
    was un-favourited.
    """
    existing = Favorite.objects.filter(customer=customer, product=product).first()
    if existing is not None:
        existing.delete()
        return None, False

    favorite = Favorite.objects.create(
        tenant_id=product.tenant_id, customer=customer, product=product
    )
    return favorite, True


def register_product_view(product: Product) -> None:
    """Increment the view counter without a read-modify-write race."""
    from django.db.models import F

    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)


def assert_purchasable(product: Product) -> None:
    """Guard used by cart and checkout."""
    if not product.is_purchasable:
        raise ProductNotPurchasableError(details={"product_id": str(product.pk)})


def localized_field(obj: Any, field: str, locale: str | None) -> str:
    """Return a translated field value, falling back to the default language.

    Translations are optional: a merchant selling only in pt-BR never has to
    fill them in, and the storefront still renders.
    """
    default = getattr(obj, field, "") or ""
    if not locale:
        return default

    translations = getattr(obj, "translations", None)
    if translations is None:
        return default

    normalised = locale.lower()
    for translation in translations.all():
        if translation.locale.lower() == normalised:
            return getattr(translation, field, "") or default
    # Try the bare language ("en" for "en-GB") before giving up.
    language = normalised.split("-")[0]
    for translation in translations.all():
        if translation.locale.lower().split("-")[0] == language:
            return getattr(translation, field, "") or default
    return default
