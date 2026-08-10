"""
Order models.

An order is the platform's financial record, and it is built on snapshots. Every
line stores the product name, SKU, unit and price *as they were at checkout*.
When a product later costs R$12, an order placed at R$10 still says R$10
(invariants #2, #3, #10).

The FK to ``Product`` is kept for reporting and uses ``SET_NULL``: archiving a
product must never destroy the history of what was sold.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel, TenantQuerySet
from apps.common.money import quantize_money

from .constants import ACTIVE_STATUSES, CUSTOMER_CANCELLABLE_STATUSES, OrderStatus


class OrderQuerySet(TenantQuerySet):
    """Order queries. Extends ``TenantQuerySet`` to keep ``for_tenant()``."""

    def revenue_generating(self) -> OrderQuerySet:
        from .constants import REVENUE_STATUSES

        return self.filter(status__in=REVENUE_STATUSES)

    def active(self) -> OrderQuerySet:
        return self.filter(status__in=ACTIVE_STATUSES)

    def with_details(self) -> OrderQuerySet:
        return self.select_related("customer", "address").prefetch_related(
            "items", "status_history", "payments"
        )


class Order(TenantOwnedModel):
    """A placed order."""

    number = models.CharField(_("order number"), max_length=32, db_index=True)
    customer = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("customer"),
    )

    # Contact snapshot: an anonymised account must not erase who an order was
    # for while it is still being fulfilled.
    customer_name = models.CharField(_("customer name"), max_length=255, blank=True)
    customer_email = models.EmailField(_("customer email"), blank=True)
    customer_phone = models.CharField(_("customer phone"), max_length=32, blank=True)

    status = models.CharField(
        _("status"), max_length=24, choices=OrderStatus.choices, default=OrderStatus.DRAFT
    )
    delivery_method = models.CharField(_("delivery method"), max_length=16, default="PICKUP")

    # --- Money ---------------------------------------------------------------
    currency = models.CharField(_("currency"), max_length=3, default="BRL")
    subtotal = models.DecimalField(
        _("subtotal"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_total = models.DecimalField(
        _("discount"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    delivery_fee = models.DecimalField(
        _("delivery fee"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_total = models.DecimalField(
        _("tax"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        _("total"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    refunded_total = models.DecimalField(
        _("refunded"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    coupon_code = models.CharField(_("coupon"), max_length=32, blank=True)
    customer_note = models.CharField(_("customer note"), max_length=500, blank=True)
    internal_note = models.TextField(_("internal note"), blank=True)

    scheduled_for = models.DateTimeField(_("scheduled for"), null=True, blank=True)
    estimated_ready_at = models.DateTimeField(_("estimated ready at"), null=True, blank=True)

    placed_at = models.DateTimeField(_("placed at"), null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancellation_reason = models.CharField(_("cancellation reason"), max_length=255, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_order_tenant_number"),
            models.CheckConstraint(
                condition=models.Q(total__gte=0), name="order_total_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(refunded_total__lte=models.F("total")),
                name="order_refund_within_total",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "customer", "-created_at"]),
            models.Index(fields=["tenant", "-placed_at"]),
        ]

    def __str__(self) -> str:
        return self.number

    # --- Derived state -------------------------------------------------------
    @property
    def is_paid(self) -> bool:
        return self.paid_at is not None

    @property
    def is_cancellable_by_customer(self) -> bool:
        return self.status in CUSTOMER_CANCELLABLE_STATUSES

    @property
    def net_total(self) -> Decimal:
        """What the merchant actually keeps after refunds."""
        return quantize_money(self.total - self.refunded_total)

    @property
    def item_count(self) -> int:
        return len(self.items.all())

    @property
    def cost_total(self) -> Decimal:
        """Cost of goods, from the per-line cost snapshots.

        Lines without a recorded cost contribute zero; the reporting layer says
        so explicitly rather than pretending the margin is complete.
        """
        return quantize_money(
            sum(
                ((item.unit_cost or Decimal("0.00")) * item.quantity for item in self.items.all()),
                Decimal("0.00"),
            )
        )

    def recalculate_total(self) -> Decimal:
        """Derive the total from its parts. Never trusts a client-sent value."""
        self.total = quantize_money(
            self.subtotal - self.discount_total + self.delivery_fee + self.tax_total
        )
        return self.total


class OrderItem(TenantOwnedModel):
    """One line of an order, frozen at checkout."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("order")
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )

    # Snapshot of the product at the moment of purchase.
    product_name = models.CharField(_("product"), max_length=255)
    product_sku = models.CharField(_("SKU"), max_length=64, blank=True)
    unit_code = models.CharField(_("unit"), max_length=12, blank=True)
    category_name = models.CharField(_("category"), max_length=120, blank=True)

    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(_("unit price"), max_digits=12, decimal_places=2)
    base_unit_price = models.DecimalField(
        _("list price"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    unit_cost = models.DecimalField(
        _("unit cost"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Captured for margin reporting. Never shown to customers."),
    )
    discount_amount = models.DecimalField(
        _("discount"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    line_total = models.DecimalField(_("line total"), max_digits=12, decimal_places=2)

    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="order_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0), name="order_item_price_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "product"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.quantity} × {self.product_name}"

    @property
    def margin(self) -> Decimal | None:
        if self.unit_cost is None:
            return None
        return quantize_money((self.unit_price - self.unit_cost) * self.quantity)


class OrderAddress(TenantOwnedModel):
    """Immutable delivery address copied onto the order."""

    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="address", verbose_name=_("order")
    )
    recipient_name = models.CharField(_("recipient"), max_length=160)
    postal_code = models.CharField(_("postal code"), max_length=16)
    street = models.CharField(_("street"), max_length=255)
    number = models.CharField(_("number"), max_length=32)
    complement = models.CharField(_("complement"), max_length=120, blank=True)
    neighborhood = models.CharField(_("neighborhood"), max_length=120)
    city = models.CharField(_("city"), max_length=120)
    state = models.CharField(_("state"), max_length=64)
    country = models.CharField(_("country"), max_length=2, default="BR")
    reference = models.CharField(_("reference point"), max_length=255, blank=True)
    latitude = models.DecimalField(
        _("latitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        _("longitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )

    class Meta:
        verbose_name = _("order address")
        verbose_name_plural = _("order addresses")

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.street}, {self.number}"

    @property
    def one_line(self) -> str:
        parts = [f"{self.street}, {self.number}", self.neighborhood, f"{self.city}/{self.state}"]
        return " — ".join(part for part in parts if part)


class OrderStatusHistory(TenantOwnedModel):
    """Every state change, in order. The customer timeline reads from here."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_history", verbose_name=_("order")
    )
    old_status = models.CharField(_("previous status"), max_length=24, blank=True)
    new_status = models.CharField(_("new status"), max_length=24)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_label = models.CharField(_("actor"), max_length=255, blank=True)
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    is_customer_visible = models.BooleanField(_("visible to the customer"), default=True)

    class Meta:
        verbose_name = _("order status history")
        verbose_name_plural = _("order status history")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["order", "created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.old_status} → {self.new_status}"

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk and not self._state.adding:
            raise ValueError("Order status history is immutable.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class OrderNote(TenantOwnedModel):
    """A staff note attached to an order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    body = models.TextField(_("note"))
    is_customer_visible = models.BooleanField(_("visible to the customer"), default=False)

    class Meta:
        verbose_name = _("order note")
        verbose_name_plural = _("order notes")
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.body[:60]
