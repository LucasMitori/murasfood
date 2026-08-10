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

from apps.common.money import (
    gross_margin,
    gross_margin_percentage,
    markup_percentage,
    money_str,
)

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


#: Fields a shopper is allowed to see the history of.
#:
#: An allow-list rather than "everything except cost_price". A new field added
#: to the history later is invisible here until someone decides it is public,
#: which is the safe direction for the mistake to go.
PUBLIC_PRICE_FIELDS: tuple[str, ...] = ("base_price", "sale_price")

#: Longest window the public chart will serve, in days.
MAX_PUBLIC_HISTORY_DAYS = 365


def public_price_series(product: Product, *, days: int = 90) -> dict[str, Any]:
    """Shelf-price movement for the product page chart.

    Deliberately narrow. The staff endpoint returns whole ``PriceHistory`` rows
    — cost changes, who made them, internal notes — none of which belongs on a
    public page. This returns dated shelf prices and nothing else.

    Points are the prices the product *changed to*, so the series is what a
    shopper would have seen on the shelf on that date.
    """
    from .models import PriceHistory

    window = max(1, min(int(days), MAX_PUBLIC_HISTORY_DAYS))
    since = timezone.now() - timezone.timedelta(days=window)

    rows = (
        PriceHistory.objects.filter(
            product=product,
            field__in=PUBLIC_PRICE_FIELDS,
            created_at__gte=since,
            new_value__isnull=False,
        )
        .order_by("created_at")
        .values_list("created_at", "new_value")
    )

    points = [
        {"date": created_at.date().isoformat(), "price": money_str(value)}
        for created_at, value in rows
    ]

    values = [Decimal(point["price"]) for point in points]
    resolved = resolve_price(product)

    # The chart is drawn against the price on sale now, which is authoritative
    # even when no change has been recorded inside the window.
    current = resolved.unit_price if resolved else (values[-1] if values else None)

    summary: dict[str, str | None] = {
        "current": money_str(current) if current is not None else None,
        "lowest": money_str(min(values)) if values else None,
        "highest": money_str(max(values)) if values else None,
        "average": money_str(sum(values) / len(values)) if values else None,
        "change_percentage": None,
    }

    # Movement across the window, from the first recorded price to today's.
    if values and current is not None and values[0] > 0:
        delta = (current - values[0]) / values[0] * 100
        summary["change_percentage"] = f"{delta.quantize(Decimal('0.01'))}"

    return {"days": window, "points": points, "summary": summary}
