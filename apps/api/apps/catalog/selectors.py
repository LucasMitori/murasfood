"""Catalog read queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Count, F, Prefetch, Q, QuerySet

from apps.pricing.selectors import annotate_effective_price

from .constants import PRODUCT_SORT_OPTIONS
from .models import Category, Product, ProductImage

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User


def storefront_products(tenant_id: Any) -> QuerySet[Product]:
    """Base queryset for anything a customer sees.

    Prefetches images, brand, category and unit, and annotates the effective
    price so listing, sorting and filtering by price all stay in SQL.
    """
    return annotate_effective_price(
        Product.objects.for_tenant(tenant_id)
        .purchasable()
        .select_related("category", "brand", "sale_unit", "inventory")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.select_related("asset").order_by(
                    "-is_primary", "position"
                ),
            ),
            "tags",
            "translations",
        )
    )


def admin_products(tenant_id: Any) -> QuerySet[Product]:
    """Every product, including drafts and archived items."""
    return annotate_effective_price(
        Product.objects.for_tenant(tenant_id)
        .with_relations()
        .select_related("inventory")
        .prefetch_related("translations")
    )


def apply_sort(queryset: QuerySet, sort: str | None) -> QuerySet:
    """Apply a whitelisted sort.

    User input never reaches ``order_by`` directly: an arbitrary field name
    would let a caller sort by ``cost_price`` and read margins off a public
    endpoint.
    """
    fields = PRODUCT_SORT_OPTIONS.get(sort or "relevance")
    if not fields:
        fields = PRODUCT_SORT_OPTIONS["relevance"]
    return queryset.order_by(*fields)


def featured_products(tenant_id: Any, *, limit: int = 12) -> QuerySet[Product]:
    return storefront_products(tenant_id).filter(is_featured=True)[:limit]


def best_sellers(tenant_id: Any, *, limit: int = 12) -> QuerySet[Product]:
    return storefront_products(tenant_id).order_by("-sales_count", "name")[:limit]


def new_arrivals(tenant_id: Any, *, limit: int = 12) -> QuerySet[Product]:
    return storefront_products(tenant_id).order_by("-created_at")[:limit]


def discounted_products(tenant_id: Any, *, limit: int = 12) -> QuerySet[Product]:
    """Products whose promotional price is currently below the base price."""
    return (
        storefront_products(tenant_id)
        .filter(sale_price__isnull=False, sale_price__lt=F("base_price"))
        .order_by("-updated_at")[:limit]
    )


def related_products(product: Product, *, limit: int = 8) -> QuerySet[Product]:
    """Simple rule-based recommendations (spec §54): same category, not itself.

    Deliberately not machine learning. The signature is the extension point:
    a smarter implementation can replace the body without touching callers.
    """
    return (
        storefront_products(product.tenant_id)
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)
        .order_by("-sales_count")[:limit]
    )


def category_tree(tenant_id: Any, *, only_active: bool = True) -> list[Category]:
    """Root categories with their children and product counts, in one pass."""
    queryset = Category.objects.for_tenant(tenant_id)
    if only_active:
        queryset = queryset.filter(is_active=True)

    children_qs = queryset.order_by("position", "name")
    roots = (
        queryset.filter(parent__isnull=True)
        .prefetch_related(Prefetch("children", queryset=children_qs))
        .annotate(
            product_count=Count(
                "products",
                filter=Q(products__is_active=True, products__status="ACTIVE"),
                distinct=True,
            )
        )
        .order_by("position", "name")
    )
    return list(roots)


def descendant_category_ids(category: Category) -> list[Any]:
    """The category and its children — a listing includes subcategories.

    Depth is capped at two levels, matching what the storefront navigation
    renders.
    """
    ids = [category.pk]
    ids.extend(category.children.values_list("pk", flat=True))
    return ids


def favorite_product_ids(customer: User | None, tenant_id: Any) -> set[Any]:
    """Ids of the products a customer has saved, for badge rendering."""
    if customer is None or not getattr(customer, "is_authenticated", False):
        return set()
    from .models import Favorite

    return set(
        Favorite.objects.filter(customer=customer, tenant_id=tenant_id).values_list(
            "product_id", flat=True
        )
    )


def product_by_slug(tenant_id: Any, slug: str) -> Product | None:
    return storefront_products(tenant_id).filter(slug=slug).first()


def product_by_barcode(tenant_id: Any, code: str) -> Product | None:
    """Barcode lookup, for the future in-app scanner (spec §90)."""
    return storefront_products(tenant_id).filter(barcodes__code=code.strip()).first()
