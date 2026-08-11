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


class ShoppingList(TenantOwnedModel):
    """A reusable set of products a customer buys regularly.

    Distinct from a cart in two ways that matter. It has no lifecycle — it is
    never converted, never expires, and survives checkout — and it carries no
    availability or pricing meaning. A list is a shopping *intention*; the cart
    is what is actually being bought now. Copying a list into the cart goes
    through :func:`apps.cart.services.add_list_to_cart` so that stock and
    quantity rules are enforced in exactly one place.
    """

    customer = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="shopping_lists",
        verbose_name=_("customer"),
    )
    name = models.CharField(_("name"), max_length=120)
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("shopping list")
        verbose_name_plural = _("shopping lists")
        ordering = ["name"]
        constraints = [
            # Two lists called "Mensal" would make the picker useless.
            models.UniqueConstraint(
                fields=["tenant", "customer", "name"], name="uniq_shopping_list_name"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.name

    # No `item_count` property here on purpose: the list index annotates one
    # with `Count("items")`, and a property of the same name would both shadow
    # the annotation and issue a query per row.


class ShoppingListItem(TenantOwnedModel):
    """One product on a shopping list.

    Like ``CartItem`` this stores no price. What a list is worth depends on
    when you look at it, so any total is computed on read from the pricing
    engine rather than frozen here.
    """

    shopping_list = models.ForeignKey(
        ShoppingList, on_delete=models.CASCADE, related_name="items", verbose_name=_("list")
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="shopping_list_items"
    )
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3, default=1)
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("shopping list item")
        verbose_name_plural = _("shopping list items")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["shopping_list", "product"], name="uniq_shopping_list_item_product"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="shopping_list_item_quantity_positive"
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
    def line_total(self) -> Decimal:
        from apps.common.money import money_multiply

        return money_multiply(self.unit_price, self.quantity)

    @property
    def is_available(self) -> bool:
        """Whether this line could be added to a cart right now."""
        from apps.inventory.services import check_availability

        return self.product.is_purchasable and check_availability(self.product, self.quantity)
