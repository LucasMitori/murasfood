"""Price mutations. Every change writes history."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.audit.services import record_audit
from apps.common.exceptions import DomainError
from apps.common.money import quantize_money

from .models import PriceChangeReason, PriceHistory, PriceList, ProductPrice

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.catalog.models import Product
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.pricing")


class InvalidPriceError(DomainError):
    default_detail = _("The price is invalid.")
    default_code = "INVALID_PRICE"


def default_price_list(tenant: Tenant) -> PriceList:
    """The tenant's default list, created on first use."""
    price_list = PriceList.objects.filter(tenant=tenant, is_default=True).first()
    if price_list is None:
        price_list = PriceList.objects.create(
            tenant=tenant, name="Default", code="default", is_default=True
        )
    return price_list


def _record(
    *,
    tenant: Tenant,
    product: Product,
    price: ProductPrice | None,
    field: str,
    old: Decimal | None,
    new: Decimal | None,
    reason: str,
    actor: User | None,
    note: str = "",
) -> None:
    """Append one history row. Called for every field that actually changed."""
    if old == new:
        return
    PriceHistory.objects.create(
        tenant=tenant,
        product=product,
        price=price,
        field=field,
        old_value=old,
        new_value=new,
        reason=reason,
        note=note[:255],
        changed_by=actor,
    )


@transaction.atomic
def set_price(
    *,
    tenant: Tenant,
    product: Product,
    base_price: Decimal | str,
    sale_price: Decimal | str | None = None,
    cost_price: Decimal | str | None = None,
    min_quantity: Decimal | str = Decimal("1.000"),
    starts_at: Any = None,
    ends_at: Any = None,
    reason: str = PriceChangeReason.MANUAL,
    actor: User | None = None,
    note: str = "",
) -> ProductPrice:
    """Create or update the price row for a product and quantity tier.

    Updating in place (rather than superseding rows) keeps the table small; the
    audit trail lives in ``PriceHistory``, which is append-only, so nothing is
    lost (invariant #10).
    """
    base = quantize_money(base_price)
    sale = quantize_money(sale_price) if sale_price is not None else None
    cost = quantize_money(cost_price) if cost_price is not None else None
    tier = Decimal(str(min_quantity))

    if base < 0:
        raise InvalidPriceError(_("The base price cannot be negative."))
    if sale is not None and sale > base:
        raise InvalidPriceError(
            _("The promotional price cannot exceed the base price."),
            details={"base_price": str(base), "sale_price": str(sale)},
        )

    price_list = default_price_list(tenant)
    existing = (
        ProductPrice.objects.select_for_update()
        .filter(tenant=tenant, product=product, price_list=price_list, min_quantity=tier)
        .first()
    )

    if existing is None:
        price = ProductPrice.objects.create(
            tenant=tenant,
            product=product,
            price_list=price_list,
            base_price=base,
            sale_price=sale,
            cost_price=cost,
            min_quantity=tier,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        _record(
            tenant=tenant,
            product=product,
            price=price,
            field="base_price",
            old=None,
            new=base,
            reason=PriceChangeReason.INITIAL if reason == PriceChangeReason.MANUAL else reason,
            actor=actor,
            note=note,
        )
        if sale is not None:
            _record(
                tenant=tenant,
                product=product,
                price=price,
                field="sale_price",
                old=None,
                new=sale,
                reason=reason,
                actor=actor,
                note=note,
            )
    else:
        price = existing
        _record(
            tenant=tenant,
            product=product,
            price=price,
            field="base_price",
            old=price.base_price,
            new=base,
            reason=reason,
            actor=actor,
            note=note,
        )
        _record(
            tenant=tenant,
            product=product,
            price=price,
            field="sale_price",
            old=price.sale_price,
            new=sale,
            reason=reason,
            actor=actor,
            note=note,
        )
        _record(
            tenant=tenant,
            product=product,
            price=price,
            field="cost_price",
            old=price.cost_price,
            new=cost,
            reason=PriceChangeReason.COST_CHANGE,
            actor=actor,
            note=note,
        )

        price.base_price = base
        price.sale_price = sale
        price.cost_price = cost
        price.starts_at = starts_at
        price.ends_at = ends_at
        price.is_active = True
        price.save()

    record_audit(
        action="pricing.price_changed",
        tenant=tenant,
        actor=actor,
        resource=product,
        new_values={
            "base_price": str(base),
            "sale_price": str(sale) if sale is not None else None,
            "min_quantity": str(tier),
        },
    )
    logger.info(
        "price_changed",
        extra={"event": "pricing.changed", "product_id": str(product.pk), "base_price": str(base)},
    )
    return price


@transaction.atomic
def bulk_adjust_prices(
    *,
    tenant: Tenant,
    products: list[Product],
    percentage: Decimal,
    actor: User | None = None,
    note: str = "",
) -> int:
    """Shift a set of prices by a percentage (e.g. a 5% increase).

    Each product still goes through :func:`set_price`, so every row lands in the
    history — a bulk operation is not an excuse to skip the audit trail.
    """
    factor = (Decimal("100") + Decimal(str(percentage))) / Decimal("100")
    if factor <= 0:
        raise InvalidPriceError(_("The adjustment would produce a non-positive price."))

    changed = 0
    for product in products:
        current = (
            ProductPrice.objects.filter(
                tenant=tenant, product=product, min_quantity=Decimal("1.000")
            )
            .order_by("-created_at")
            .first()
        )
        if current is None:
            continue
        set_price(
            tenant=tenant,
            product=product,
            base_price=quantize_money(current.base_price * factor),
            sale_price=(
                quantize_money(current.sale_price * factor)
                if current.sale_price is not None
                else None
            ),
            cost_price=current.cost_price,
            reason=PriceChangeReason.MANUAL,
            actor=actor,
            note=note or f"Bulk adjustment {percentage}%",
        )
        changed += 1
    return changed


def deactivate_price(price: ProductPrice, *, actor: User | None = None) -> None:
    """Retire a price row without deleting its history."""
    _record(
        tenant=price.tenant,
        product=price.product,
        price=price,
        field="is_active",
        old=Decimal("1"),
        new=Decimal("0"),
        reason=PriceChangeReason.MANUAL,
        actor=actor,
    )
    price.is_active = False
    price.save(update_fields=["is_active", "updated_at"])
