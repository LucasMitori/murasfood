"""
Delivery quoting.

:func:`quote_delivery` is the single source of truth for what a customer pays to
have an order delivered. The cart preview and checkout both call it, so the fee
shown is the fee charged — the frontend never supplies an amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from apps.common.exceptions import DomainError
from apps.common.money import quantize_money

from .models import DeliveryMethod, DeliverySettings, DeliveryZone

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

ZERO = Decimal("0.00")


class DeliveryUnavailableError(DomainError):
    default_detail = _("Delivery is not available for this address.")
    default_code = "DELIVERY_UNAVAILABLE"


class MinimumOrderNotMetError(DomainError):
    default_detail = _("The order is below the minimum amount.")
    default_code = "MINIMUM_ORDER_NOT_MET"


@dataclass(frozen=True)
class DeliveryQuote:
    """A priced delivery option."""

    method: str
    fee: Decimal
    estimated_minutes: int
    minimum_order_amount: Decimal
    zone_id: Any | None = None
    zone_name: str = ""
    is_free: bool = False


def get_settings(tenant: Tenant) -> DeliverySettings:
    """Delivery configuration, created with defaults on first use."""
    settings, _created = DeliverySettings.objects.get_or_create(tenant=tenant)
    return settings


def find_zone(tenant: Tenant, postal_code: str) -> DeliveryZone | None:
    """The narrowest active zone covering a CEP.

    Narrowest first, so a specific street range beats a broad city-wide zone.
    """
    digits = "".join(ch for ch in (postal_code or "") if ch.isdigit())
    if len(digits) != 8:
        return None

    zones = DeliveryZone.objects.filter(
        tenant=tenant,
        is_active=True,
        postal_code_start__lte=digits,
        postal_code_end__gte=digits,
    )
    return min(
        zones,
        key=lambda zone: int(zone.postal_code_end) - int(zone.postal_code_start),
        default=None,
    )


def quote_delivery(
    *,
    tenant: Tenant,
    method: str,
    subtotal: Decimal,
    postal_code: str = "",
) -> DeliveryQuote:
    """Price one delivery option.

    Raises:
        DeliveryUnavailableError: The method is disabled or the address is
            outside every configured zone.
        MinimumOrderNotMetError: The subtotal is below the applicable minimum.
    """
    settings = get_settings(tenant)
    subtotal = quantize_money(subtotal)

    if method == DeliveryMethod.PICKUP:
        if not settings.pickup_enabled:
            raise DeliveryUnavailableError(_("Pickup is not available."), code="PICKUP_UNAVAILABLE")
        if subtotal < settings.minimum_order_amount:
            raise MinimumOrderNotMetError(
                details={"minimum_order_amount": str(settings.minimum_order_amount)}
            )
        return DeliveryQuote(
            method=DeliveryMethod.PICKUP,
            fee=ZERO,
            estimated_minutes=settings.estimated_pickup_minutes,
            minimum_order_amount=settings.minimum_order_amount,
            is_free=True,
        )

    if not settings.delivery_enabled:
        raise DeliveryUnavailableError()

    zone = find_zone(tenant, postal_code) if postal_code else None
    if (
        postal_code
        and zone is None
        and DeliveryZone.objects.filter(tenant=tenant, is_active=True).exists()
    ):
        # Zones are configured and none matched: the address is out of area.
        raise DeliveryUnavailableError(details={"postal_code": postal_code})

    fee = quantize_money(zone.fee if zone else settings.base_fee)
    minimum = quantize_money(zone.minimum_order_amount if zone else settings.minimum_order_amount)
    threshold = zone.free_delivery_threshold if zone else settings.free_delivery_threshold
    estimated = zone.estimated_minutes if zone else settings.estimated_delivery_minutes

    if subtotal < minimum:
        raise MinimumOrderNotMetError(details={"minimum_order_amount": str(minimum)})

    is_free = threshold is not None and subtotal >= threshold
    return DeliveryQuote(
        method=DeliveryMethod.DELIVERY,
        fee=ZERO if is_free else fee,
        estimated_minutes=estimated,
        minimum_order_amount=minimum,
        zone_id=zone.pk if zone else None,
        zone_name=zone.name if zone else "",
        is_free=is_free,
    )


def available_methods(
    tenant: Tenant, *, subtotal: Decimal, postal_code: str = ""
) -> list[dict[str, Any]]:
    """Every option the customer can pick, priced, with reasons for exclusions."""
    options: list[dict[str, Any]] = []
    for method in (DeliveryMethod.PICKUP, DeliveryMethod.DELIVERY):
        try:
            quote = quote_delivery(
                tenant=tenant, method=method, subtotal=subtotal, postal_code=postal_code
            )
        except DomainError as exc:
            options.append(
                {
                    "method": method,
                    "available": False,
                    "reason": exc.default_code,
                    "message": str(exc.detail),
                }
            )
            continue

        options.append(
            {
                "method": quote.method,
                "available": True,
                "fee": str(quote.fee),
                "is_free": quote.is_free,
                "estimated_minutes": quote.estimated_minutes,
                "minimum_order_amount": str(quote.minimum_order_amount),
                "zone": quote.zone_name or None,
            }
        )
    return options


def public_delivery_config(tenant: Tenant) -> dict[str, Any]:
    """Delivery information for the storefront bootstrap payload."""
    settings = get_settings(tenant)
    return {
        "delivery_enabled": settings.delivery_enabled,
        "pickup_enabled": settings.pickup_enabled,
        "minimum_order_amount": str(settings.minimum_order_amount),
        "base_fee": str(settings.base_fee),
        "free_delivery_threshold": (
            str(settings.free_delivery_threshold)
            if settings.free_delivery_threshold is not None
            else None
        ),
        "estimated_delivery_minutes": settings.estimated_delivery_minutes,
        "estimated_pickup_minutes": settings.estimated_pickup_minutes,
        "service_radius_km": str(settings.service_radius_km),
    }
