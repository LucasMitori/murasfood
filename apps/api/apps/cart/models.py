"""
Cart models.

A cart is *not* a financial record (spec §15). It stores intent — which products
and how many — and prices are re-resolved on every read. That is why
``CartItem`` has no price column: a stale price in a cart that a customer left
open for a week must never become the price they pay. The immutable snapshot is
taken once, at checkout, on the order.

Anonymous carts are addressed by an opaque token the client stores; signed-in
carts belong to the customer, and the two merge at login.
"""

from __future__ import annotations

import secrets
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel
from apps.common.money import quantize_money


def generate_cart_token() -> str:
    return secrets.token_urlsafe(24)


class CartStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    CONVERTED = "CONVERTED", _("Converted to an order")
    ABANDONED = "ABANDONED", _("Abandoned")
    MERGED = "MERGED", _("Merged into another cart")


class Cart(TenantOwnedModel):
    """One shopping session."""

    customer = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
        verbose_name=_("customer"),
    )
    token = models.CharField(
        _("token"),
        max_length=64,
        default=generate_cart_token,
        db_index=True,
        help_text=_("Opaque identifier for anonymous carts."),
    )
    status = models.CharField(
        _("status"), max_length=12, choices=CartStatus.choices, default=CartStatus.ACTIVE
    )
    coupon_code = models.CharField(_("coupon"), max_length=32, blank=True)
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ["-updated_at"]
        constraints = [
            # A signed-in customer has at most one active cart per tenant.
            models.UniqueConstraint(
                fields=["tenant", "customer"],
                condition=models.Q(status="ACTIVE", customer__isnull=False),
                name="uniq_active_cart_per_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-updated_at"]),
            models.Index(fields=["token", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"Cart {self.pk}"

    @property
    def item_count(self) -> int:
        return len(self.items.all())

    @property
    def total_quantity(self) -> Decimal:
        return sum((item.quantity for item in self.items.all()), Decimal("0.000"))

    @property
    def subtotal(self) -> Decimal:
        """Sum of line totals at *current* prices."""
        return quantize_money(sum((item.line_total for item in self.items.all()), Decimal("0.00")))

    @property
    def is_empty(self) -> bool:
        return not self.items.exists()


class CartItem(TenantOwnedModel):
    """One product in a cart.

    Only the quantity is persisted. ``unit_price`` is a computed property that
    consults the pricing engine, so a promotion starting overnight is reflected
    the next time the customer opens their cart.
    """

    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("cart")
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="cart_items"
    )
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3)
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="uniq_cart_item_product"),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="cart_item_quantity_positive"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.quantity} × {self.product}"

    @property
    def unit_price(self) -> Decimal:
        """Current unit price, or zero when the product has no active price."""
        from apps.pricing.selectors import resolve_price

        resolved = resolve_price(self.product, quantity=self.quantity)
        return resolved.unit_price if resolved else Decimal("0.00")

    @property
    def base_unit_price(self) -> Decimal:
        from apps.pricing.selectors import resolve_price

        resolved = resolve_price(self.product, quantity=self.quantity)
        return resolved.base_price if resolved else Decimal("0.00")

    @property
    def line_total(self) -> Decimal:
        from apps.common.money import money_multiply

        return money_multiply(self.unit_price, self.quantity)

    @property
    def is_available(self) -> bool:
        """Whether this line could be checked out right now."""
        from apps.inventory.services import check_availability

        return self.product.is_purchasable and check_availability(self.product, self.quantity)
