"""Cart operations."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.catalog.services import assert_purchasable
from apps.common.exceptions import DomainError, InsufficientStockError
from apps.common.money import quantize_quantity

from .models import Cart, CartItem, CartStatus

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.catalog.models import Product

logger = logging.getLogger("murasfood.cart")


class CartError(DomainError):
    default_detail = _("The cart could not be updated.")
    default_code = "CART_ERROR"


def _validate_quantity(product: Product, quantity: Decimal) -> Decimal:
    """Round to the unit's precision and enforce per-product limits.

    A product sold by unit cannot be ordered in halves; one sold by weight can.
    """
    quantity = quantize_quantity(quantity)
    if quantity <= 0:
        raise CartError(_("The quantity must be greater than zero."), code="INVALID_QUANTITY")

    if not product.sells_fractional_quantity and quantity != quantity.to_integral_value():
        raise CartError(_("This product is sold in whole units."), code="FRACTIONAL_NOT_ALLOWED")

    limit = product.max_quantity_per_order
    if limit is not None and quantity > limit:
        raise CartError(
            _("The maximum quantity for this product is %(limit)s.") % {"limit": limit},
            code="QUANTITY_LIMIT_EXCEEDED",
            details={"max_quantity": str(limit)},
        )
    return quantity


@transaction.atomic
def add_item(
    *, cart: Cart, product: Product, quantity: Decimal | str | int = 1, note: str = ""
) -> CartItem:
    """Add a product, or increase its quantity when already present.

    Availability is checked advisory-only here; the authoritative reservation
    happens at checkout under a row lock (invariant #6).
    """
    from apps.inventory.services import check_availability

    if product.tenant_id != cart.tenant_id:
        raise CartError(_("Product not found."), code="NOT_FOUND", status_code=404)
    assert_purchasable(product)

    requested = _validate_quantity(product, Decimal(str(quantity)))
    item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
    new_quantity = _validate_quantity(
        product, (item.quantity if item else Decimal("0")) + requested
    )

    if not check_availability(product, new_quantity):
        raise InsufficientStockError(
            details={"product": product.name, "requested": str(new_quantity)}
        )

    if item is None:
        item = CartItem.objects.create(
            tenant_id=cart.tenant_id,
            cart=cart,
            product=product,
            quantity=new_quantity,
            note=note[:255],
        )
    else:
        item.quantity = new_quantity
        if note:
            item.note = note[:255]
        item.save(update_fields=["quantity", "note", "updated_at"])

    cart.save(update_fields=["updated_at"])
    return item


@transaction.atomic
def set_item_quantity(
    *, cart: Cart, item: CartItem, quantity: Decimal | str | int
) -> CartItem | None:
    """Set an absolute quantity. Zero removes the line."""
    from apps.inventory.services import check_availability

    if item.cart_id != cart.pk:
        raise CartError(_("Item not found."), code="NOT_FOUND", status_code=404)

    requested = quantize_quantity(quantity)
    if requested <= 0:
        item.delete()
        cart.save(update_fields=["updated_at"])
        return None

    requested = _validate_quantity(item.product, requested)
    if not check_availability(item.product, requested):
        raise InsufficientStockError(
            details={"product": item.product.name, "requested": str(requested)}
        )

    item.quantity = requested
    item.save(update_fields=["quantity", "updated_at"])
    cart.save(update_fields=["updated_at"])
    return item


def remove_item(*, cart: Cart, item: CartItem) -> None:
    if item.cart_id != cart.pk:
        raise CartError(_("Item not found."), code="NOT_FOUND", status_code=404)
    item.delete()
    cart.save(update_fields=["updated_at"])


def clear_cart(cart: Cart) -> None:
    cart.items.all().delete()
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code", "updated_at"])


def apply_coupon(*, cart: Cart, code: str) -> Cart:
    """Attach a coupon after validating it against the current cart."""
    from apps.promotions.services import validate_coupon

    coupon = validate_coupon(
        tenant=cart.tenant, code=code, customer=cart.customer, subtotal=cart.subtotal
    )
    cart.coupon_code = coupon.code
    cart.save(update_fields=["coupon_code", "updated_at"])
    return cart


def remove_coupon(cart: Cart) -> Cart:
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code", "updated_at"])
    return cart


def cart_discount_preview(cart: Cart, *, coupon_code: str = "") -> Any:
    from .selectors import cart_discount_result

    return cart_discount_result(cart, coupon_code=coupon_code or cart.coupon_code)


@transaction.atomic
def merge_carts(*, anonymous_cart: Cart, customer: User) -> Cart:
    """Fold an anonymous cart into the customer's cart at sign-in.

    Quantities are *summed* rather than replaced: a customer who added two
    loaves before signing in and one after expects three, not one. Merging is
    capped by availability, and the anonymous cart is marked ``MERGED`` rather
    than deleted so the action stays traceable.
    """
    from apps.inventory.services import check_availability

    if anonymous_cart.customer_id is not None:
        return anonymous_cart

    target = (
        Cart.objects.filter(
            tenant_id=anonymous_cart.tenant_id, customer=customer, status=CartStatus.ACTIVE
        )
        .select_for_update()
        .first()
    )
    if target is None:
        anonymous_cart.customer = customer
        anonymous_cart.save(update_fields=["customer", "updated_at"])
        return anonymous_cart

    for item in anonymous_cart.items.select_related("product").all():
        existing = CartItem.objects.filter(cart=target, product=item.product).first()
        merged_quantity = (existing.quantity if existing else Decimal("0")) + item.quantity

        if not check_availability(item.product, merged_quantity):
            # Keep what is possible instead of failing the whole sign-in.
            merged_quantity = existing.quantity if existing else item.quantity

        if existing is None:
            CartItem.objects.create(
                tenant_id=target.tenant_id,
                cart=target,
                product=item.product,
                quantity=merged_quantity,
                note=item.note,
            )
        else:
            existing.quantity = merged_quantity
            existing.save(update_fields=["quantity", "updated_at"])

    if anonymous_cart.coupon_code and not target.coupon_code:
        target.coupon_code = anonymous_cart.coupon_code
        target.save(update_fields=["coupon_code", "updated_at"])

    anonymous_cart.status = CartStatus.MERGED
    anonymous_cart.save(update_fields=["status", "updated_at"])

    logger.info(
        "cart_merged",
        extra={"event": "cart.merged", "source": str(anonymous_cart.pk), "target": str(target.pk)},
    )
    return target


def mark_converted(cart: Cart) -> None:
    """Close a cart once its order exists."""
    cart.status = CartStatus.CONVERTED
    cart.save(update_fields=["status", "updated_at"])
