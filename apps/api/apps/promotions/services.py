"""
The discount engine.

One entry point — :func:`calculate_discounts` — used by the cart preview *and*
by checkout, so what a customer is quoted is what they are charged. The engine
is pure: it reads promotions and returns numbers, and never mutates anything.
Counters move only in :func:`redeem_coupon`, once an order exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.exceptions import DomainError
from apps.common.money import apply_percentage, quantize_money

from .models import Coupon, CouponRedemption, DiscountType, Promotion, PromotionScope

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.orders.models import Order
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.promotions")

ZERO = Decimal("0.00")


class CouponError(DomainError):
    default_detail = _("This coupon cannot be used.")
    default_code = "INVALID_COUPON"


@dataclass(frozen=True)
class DiscountLine:
    """A discount attributed to one promotion."""

    promotion_id: Any
    promotion_name: str
    amount: Decimal
    discount_type: str
    coupon_code: str = ""


@dataclass
class DiscountResult:
    """Everything checkout needs to know about applied discounts."""

    total_discount: Decimal = ZERO
    free_delivery: bool = False
    lines: list[DiscountLine] = field(default_factory=list)
    coupon: Coupon | None = None

    @property
    def has_discount(self) -> bool:
        return self.total_discount > 0 or self.free_delivery


@dataclass(frozen=True)
class CartLine:
    """Input shape for the engine — deliberately not a model.

    Cart items and order items both convert to this, so the engine has one
    code path regardless of caller.
    """

    product_id: Any
    category_id: Any
    quantity: Decimal
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return quantize_money(self.unit_price * self.quantity)


def _eligible_lines(promotion: Promotion, lines: list[CartLine]) -> list[CartLine]:
    """The subset of the cart a promotion applies to."""
    if promotion.scope == PromotionScope.ORDER:
        return lines
    if promotion.scope == PromotionScope.PRODUCT:
        product_ids = set(promotion.products.values_list("pk", flat=True))
        return [line for line in lines if line.product_id in product_ids]
    category_ids = set(promotion.categories.values_list("pk", flat=True))
    return [line for line in lines if line.category_id in category_ids]


def _promotion_discount(promotion: Promotion, lines: list[CartLine]) -> Decimal:
    """Discount produced by one promotion over its eligible lines."""
    eligible = _eligible_lines(promotion, lines)
    if not eligible:
        return ZERO

    base = sum((line.line_total for line in eligible), ZERO)
    if base <= 0:
        return ZERO

    if promotion.discount_type == DiscountType.PERCENTAGE:
        discount = apply_percentage(base, promotion.value)
    elif promotion.discount_type == DiscountType.FIXED:
        discount = min(quantize_money(promotion.value), base)
    elif promotion.discount_type == DiscountType.BUY_X_GET_Y:
        discount = _buy_x_get_y_discount(promotion, eligible)
    else:  # FREE_DELIVERY is handled by the caller, not as a line discount
        return ZERO

    if promotion.max_discount_amount is not None:
        discount = min(discount, quantize_money(promotion.max_discount_amount))
    return min(discount, base)


def _buy_x_get_y_discount(promotion: Promotion, lines: list[CartLine]) -> Decimal:
    """Give away ``get_quantity`` items for every ``buy_quantity`` bought.

    The cheapest eligible units are the free ones, which is both the customer-
    friendly convention and the one that limits merchant exposure.
    """
    if promotion.buy_quantity <= 0 or promotion.get_quantity <= 0:
        return ZERO

    units: list[Decimal] = []
    for line in lines:
        # Fractional quantities cannot be given away as whole units.
        whole = int(line.quantity)
        units.extend([line.unit_price] * whole)

    if not units:
        return ZERO

    units.sort()
    group_size = promotion.buy_quantity + promotion.get_quantity
    free_units = (len(units) // group_size) * promotion.get_quantity
    return quantize_money(sum(units[:free_units], ZERO))


def active_promotions(tenant: Tenant, *, moment: Any = None) -> list[Promotion]:
    """Automatic promotions currently running, highest priority first."""
    now = moment or timezone.now()
    queryset = (
        Promotion.objects.filter(tenant=tenant, is_active=True, requires_coupon=False)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .prefetch_related("products", "categories")
        .order_by("-priority", "-created_at")
    )
    return [promotion for promotion in queryset if promotion.is_running(now)]


def find_coupon(tenant: Tenant, code: str) -> Coupon | None:
    return (
        Coupon.objects.filter(tenant=tenant, code=code.strip().upper())
        .select_related("promotion")
        .prefetch_related("promotion__products", "promotion__categories")
        .first()
    )


def validate_coupon(
    *, tenant: Tenant, code: str, customer: User | None, subtotal: Decimal
) -> Coupon:
    """Check a coupon and raise a specific error explaining any refusal.

    Raises:
        CouponError: Unknown, expired, exhausted, or below the minimum order.
    """
    coupon = find_coupon(tenant, code)
    if coupon is None:
        raise CouponError(_("Coupon not found."), code="COUPON_NOT_FOUND")
    if not coupon.is_redeemable():
        raise CouponError(_("This coupon is no longer valid."), code="COUPON_EXPIRED")

    if subtotal < coupon.promotion.minimum_order_amount:
        raise CouponError(
            _("This coupon requires a minimum order of %(amount)s.")
            % {"amount": coupon.promotion.minimum_order_amount},
            code="COUPON_MINIMUM_NOT_MET",
            details={"minimum_order_amount": str(coupon.promotion.minimum_order_amount)},
        )

    if customer is not None and getattr(customer, "is_authenticated", False):
        used = CouponRedemption.objects.filter(coupon=coupon, customer=customer).count()
        if coupon.max_uses_per_customer and used >= coupon.max_uses_per_customer:
            raise CouponError(_("You have already used this coupon."), code="COUPON_ALREADY_USED")

    return coupon


def calculate_discounts(
    *,
    tenant: Tenant,
    lines: list[CartLine],
    subtotal: Decimal,
    coupon_code: str = "",
    customer: User | None = None,
    moment: Any = None,
) -> DiscountResult:
    """Compute every discount that applies to a cart.

    Non-stackable promotions do not combine: the single best one wins, which is
    what customers expect and what keeps the merchant's exposure predictable.
    Stackable promotions add on top.
    """
    result = DiscountResult()
    if not lines or subtotal <= 0:
        return result

    candidates: list[tuple[Promotion, str]] = [
        (promotion, "") for promotion in active_promotions(tenant, moment=moment)
    ]

    if coupon_code:
        coupon = validate_coupon(
            tenant=tenant, code=coupon_code, customer=customer, subtotal=subtotal
        )
        result.coupon = coupon
        candidates.append((coupon.promotion, coupon.code))

    stackable: list[DiscountLine] = []
    exclusive: list[DiscountLine] = []

    for promotion, code in candidates:
        if subtotal < promotion.minimum_order_amount:
            continue

        if promotion.discount_type == DiscountType.FREE_DELIVERY:
            result.free_delivery = True
            stackable.append(
                DiscountLine(promotion.pk, promotion.name, ZERO, promotion.discount_type, code)
            )
            continue

        amount = _promotion_discount(promotion, lines)
        if amount <= 0:
            continue

        entry = DiscountLine(promotion.pk, promotion.name, amount, promotion.discount_type, code)
        (stackable if promotion.is_stackable else exclusive).append(entry)

    if exclusive:
        best = max(exclusive, key=lambda entry: entry.amount)
        result.lines.append(best)

    result.lines.extend(stackable)
    total = sum((entry.amount for entry in result.lines), ZERO)

    # A discount can never exceed the subtotal: an order must not go negative.
    result.total_discount = min(quantize_money(total), quantize_money(subtotal))
    return result


@transaction.atomic
def redeem_coupon(*, coupon: Coupon, order: Order, discount_amount: Decimal) -> CouponRedemption:
    """Record a redemption and move the usage counters.

    ``get_or_create`` on ``(coupon, order)`` makes this idempotent: a retried
    checkout cannot burn a customer's single-use coupon twice.
    """
    redemption, created = CouponRedemption.objects.get_or_create(
        coupon=coupon,
        order=order,
        defaults={
            "tenant_id": order.tenant_id,
            "customer": order.customer,
            "discount_amount": quantize_money(discount_amount),
        },
    )
    if created:
        from django.db.models import F

        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)
        Promotion.objects.filter(pk=coupon.promotion_id).update(usage_count=F("usage_count") + 1)
        logger.info(
            "coupon_redeemed",
            extra={
                "event": "promotions.redeemed",
                "coupon": coupon.code,
                "order_id": str(order.pk),
            },
        )
    return redemption


@transaction.atomic
def revert_redemptions(order: Order) -> int:
    """Give coupon uses back when an order is cancelled before fulfilment."""
    from django.db.models import F

    reverted = 0
    for redemption in CouponRedemption.objects.filter(order=order).select_related("coupon"):
        Coupon.objects.filter(pk=redemption.coupon_id).update(
            used_count=models_greatest_zero(F("used_count") - 1)
        )
        Promotion.objects.filter(pk=redemption.coupon.promotion_id).update(
            usage_count=models_greatest_zero(F("usage_count") - 1)
        )
        redemption.delete()
        reverted += 1
    return reverted


def models_greatest_zero(expression: Any) -> Any:
    """``GREATEST(expr, 0)`` — counters are unsigned and must not underflow."""
    from django.db.models import Value
    from django.db.models.functions import Greatest

    return Greatest(expression, Value(0))
