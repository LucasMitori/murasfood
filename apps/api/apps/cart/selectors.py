"""Cart lookup and total computation."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import Prefetch

from apps.common.money import quantize_money

from .models import Cart, CartItem, CartStatus

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

CART_TOKEN_HEADER = "HTTP_X_CART_TOKEN"


def cart_queryset() -> Any:
    """Cart with everything a totals calculation needs, in one query."""
    return Cart.objects.select_related("customer").prefetch_related(
        Prefetch(
            "items",
            queryset=CartItem.objects.select_related(
                "product", "product__sale_unit", "product__category", "product__inventory"
            ).prefetch_related("product__images__asset"),
        )
    )


def current_cart_for(*, request: Any, tenant: Tenant, create: bool = True) -> Cart | None:
    """Resolve the caller's active cart.

    A signed-in customer's cart wins over any token, so signing in on a second
    device shows the same cart rather than a stale anonymous one.
    """
    user = getattr(request, "user", None)
    queryset = cart_queryset().filter(tenant=tenant, status=CartStatus.ACTIVE)

    if user is not None and getattr(user, "is_authenticated", False):
        cart = queryset.filter(customer=user).first()
        if cart is None and create:
            cart = Cart.objects.create(tenant=tenant, customer=user)
            cart = cart_queryset().get(pk=cart.pk)
        return cart

    token = _token_from_request(request)
    if token:
        cart = queryset.filter(token=token, customer__isnull=True).first()
        if cart is not None:
            return cart

    if not create:
        return None

    cart = Cart.objects.create(tenant=tenant)
    return cart_queryset().get(pk=cart.pk)


def _token_from_request(request: Any) -> str:
    meta = getattr(request, "META", {})
    header = meta.get(CART_TOKEN_HEADER, "").strip()
    if header:
        return header[:64]
    params = getattr(request, "query_params", {})
    return str(params.get("cart_token", ""))[:64] if params else ""


def cart_totals(
    cart: Cart | None,
    *,
    coupon_code: str = "",
    delivery_method: str | None = None,
    postal_code: str = "",
) -> dict[str, Any]:
    """Compute every number the cart page displays.

    Delivery is quoted only when a method is supplied, so the cart page can show
    a subtotal before the customer has chosen how to receive the order.
    """
    from apps.common.exceptions import DomainError
    from apps.delivery.selectors import quote_delivery

    if cart is None or cart.is_empty:
        zero = Decimal("0.00")
        return {
            "subtotal": str(zero),
            "discount": str(zero),
            "delivery_fee": str(zero),
            "total": str(zero),
            "item_count": 0,
            "free_delivery": False,
            "discounts": [],
            "delivery": None,
        }

    subtotal = cart.subtotal
    discounts = cart_discount_result(cart, coupon_code=coupon_code or cart.coupon_code)

    delivery_fee = Decimal("0.00")
    delivery_info: dict[str, Any] | None = None
    if delivery_method:
        try:
            quote = quote_delivery(
                tenant=cart.tenant,
                method=delivery_method,
                subtotal=subtotal - discounts.total_discount,
                postal_code=postal_code,
            )
            delivery_fee = Decimal("0.00") if discounts.free_delivery else quote.fee
            delivery_info = {
                "method": quote.method,
                "fee": str(delivery_fee),
                "estimated_minutes": quote.estimated_minutes,
                "zone": quote.zone_name or None,
            }
        except DomainError as exc:
            delivery_info = {
                "method": delivery_method,
                "error": exc.default_code,
                "message": str(exc.detail),
            }

    total = quantize_money(subtotal - discounts.total_discount + delivery_fee)

    return {
        "subtotal": str(quantize_money(subtotal)),
        "discount": str(discounts.total_discount),
        "delivery_fee": str(delivery_fee),
        "total": str(total),
        "item_count": cart.item_count,
        "free_delivery": discounts.free_delivery,
        "discounts": [
            {
                "promotion": line.promotion_name,
                "amount": str(line.amount),
                "type": line.discount_type,
                "coupon": line.coupon_code or None,
            }
            for line in discounts.lines
        ],
        "delivery": delivery_info,
    }


def cart_discount_result(cart: Cart, *, coupon_code: str = "") -> Any:
    """Run the discount engine over a cart's lines."""
    from apps.promotions.services import CartLine, calculate_discounts

    lines = [
        CartLine(
            product_id=item.product_id,
            category_id=item.product.category_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
        )
        for item in cart.items.all()
    ]
    return calculate_discounts(
        tenant=cart.tenant,
        lines=lines,
        subtotal=cart.subtotal,
        coupon_code=coupon_code,
        customer=cart.customer,
    )


def unavailable_items(cart: Cart) -> list[dict[str, Any]]:
    """Lines that would block checkout, with a reason for each.

    Surfacing these on the cart page is much kinder than failing at the payment
    step.
    """
    from apps.inventory.services import check_availability
    from apps.pricing.selectors import resolve_price

    problems: list[dict[str, Any]] = []
    for item in cart.items.all():
        if not item.product.is_purchasable:
            problems.append(
                {"item_id": str(item.pk), "product": item.product.name, "reason": "UNAVAILABLE"}
            )
        elif resolve_price(item.product, quantity=item.quantity) is None:
            problems.append(
                {"item_id": str(item.pk), "product": item.product.name, "reason": "NO_PRICE"}
            )
        elif not check_availability(item.product, item.quantity):
            problems.append(
                {"item_id": str(item.pk), "product": item.product.name, "reason": "OUT_OF_STOCK"}
            )
    return problems
