"""
Price resolution.

The single place that answers "what does this product cost right now?". Both the
storefront listing (via annotation) and the checkout (via
:func:`resolve_price`) go through here, so a customer can never see one price
and be charged another.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple

from django.db.models import DecimalField, F, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.money import gross_margin, gross_margin_percentage, markup_percentage

from .models import ProductPrice

if TYPE_CHECKING:  # pragma: no cover
    from apps.catalog.models import Product


class ResolvedPrice(NamedTuple):
    """The outcome of pricing one line."""

    unit_price: Decimal
    base_price: Decimal
    cost_price: Decimal | None
    price_id: Any | None
    is_discounted: bool

    @property
    def discount_amount(self) -> Decimal:
        return max(self.base_price - self.unit_price, Decimal("0.00"))


def _valid_window(moment: Any) -> Q:
    """Rows whose schedule contains ``moment``."""
    return (
        Q(is_active=True)
        & (Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
        & (Q(ends_at__isnull=True) | Q(ends_at__gte=moment))
    )


def price_rows_for(product: Product, *, moment: Any = None) -> QuerySet[ProductPrice]:
    """Every currently valid price row for a product, best tier first."""
    moment = moment or timezone.now()
    return ProductPrice.objects.filter(_valid_window(moment), product=product).order_by(
        "-min_quantity", "-starts_at", "-created_at"
    )


def resolve_price(
    product: Product,
    *,
    quantity: Decimal | int = 1,
    moment: Any = None,
) -> ResolvedPrice | None:
    """Resolve the unit price for ``quantity`` of ``product``.

    Chooses the highest quantity tier the order qualifies for, then prefers the
    promotional price over the base price. Returns ``None`` when the product has
    no active price at all — an unpriced product must never be sellable.
    """
    quantity = Decimal(str(quantity))
    rows = price_rows_for(product, moment=moment).filter(min_quantity__lte=quantity)

    row = rows.first()
    if row is None:
        # No tier matched (e.g. every row requires a larger quantity); fall back
        # to the plain unit price so a valid product is not made unbuyable.
        row = price_rows_for(product, moment=moment).filter(min_quantity__lte=Decimal("1")).first()
    if row is None:
        return None

    return ResolvedPrice(
        unit_price=row.effective_price,
        base_price=row.base_price,
        cost_price=row.cost_price,
        price_id=row.pk,
        is_discounted=row.is_discounted,
    )


def annotate_effective_price(queryset: QuerySet, *, moment: Any = None) -> QuerySet:
    """Annotate products with ``effective_price``, ``base_price`` and ``cost_price``.

    Done as a correlated subquery so listing, filtering and sorting by price all
    happen in the database — pulling every product into Python to sort by price
    is exactly the pattern spec §82 forbids.
    """
    moment = moment or timezone.now()
    base_rows = ProductPrice.objects.filter(
        _valid_window(moment), product=OuterRef("pk"), min_quantity__lte=Decimal("1.000")
    ).order_by("-starts_at", "-created_at")

    money = DecimalField(max_digits=12, decimal_places=2)

    return queryset.annotate(
        base_price=Subquery(base_rows.values("base_price")[:1], output_field=money),
        sale_price=Subquery(base_rows.values("sale_price")[:1], output_field=money),
        cost_price=Subquery(base_rows.values("cost_price")[:1], output_field=money),
    ).annotate(
        effective_price=Coalesce(F("sale_price"), F("base_price"), output_field=money),
    )


def margin_metrics(sale_price: Decimal, cost: Decimal | None) -> dict[str, Decimal | None]:
    """Margin, margin percentage and markup for one item.

    Margin and markup answer different questions and are routinely confused;
    both are returned so a dashboard never has to derive one from the other.
    """
    if cost is None:
        return {"gross_margin": None, "gross_margin_percentage": None, "markup_percentage": None}
    return {
        "gross_margin": gross_margin(sale_price, cost),
        "gross_margin_percentage": gross_margin_percentage(sale_price, cost),
        "markup_percentage": markup_percentage(sale_price, cost),
    }


def price_history_for(product: Product, *, limit: int = 50) -> QuerySet:
    from .models import PriceHistory

    return (
        PriceHistory.objects.filter(product=product)
        .select_related("changed_by")
        .order_by("-created_at")[:limit]
    )
