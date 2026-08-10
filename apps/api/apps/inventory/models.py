"""
Inventory models.

The rule that shapes this module: **stock is never simply overwritten**
(spec §12). Every change produces a ``StockMovement`` row, so the current
quantity is always explainable — "we are 3 short" has an answer.

Available stock is derived, not stored::

    available = quantity - reserved_quantity

``reserved_quantity`` is what pending checkouts are holding. Reservations expire
so an abandoned cart cannot lock a product out of the catalog forever.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class MovementType(models.TextChoices):
    PURCHASE = "PURCHASE", _("Purchase received")
    SALE = "SALE", _("Sale")
    RESERVATION = "RESERVATION", _("Reserved")
    RELEASE = "RELEASE", _("Reservation released")
    ADJUSTMENT = "ADJUSTMENT", _("Manual adjustment")
    CANCELLATION = "CANCELLATION", _("Order cancelled")
    RETURN = "RETURN", _("Customer return")
    LOSS = "LOSS", _("Loss or breakage")
    EXPIRATION = "EXPIRATION", _("Expired")
    INITIAL = "INITIAL", _("Opening balance")


class ReservationStatus(models.TextChoices):
    HELD = "HELD", _("Held")
    COMMITTED = "COMMITTED", _("Committed")
    RELEASED = "RELEASED", _("Released")
    EXPIRED = "EXPIRED", _("Expired")


class InventoryItem(TenantOwnedModel):
    """Stock record for one product.

    A one-to-one with ``Product`` today. When multi-branch arrives (spec §64)
    this becomes one row per product *and* location; nothing else in the schema
    needs to change.
    """

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="inventory",
        verbose_name=_("product"),
    )

    quantity = models.DecimalField(
        _("physical quantity"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )
    reserved_quantity = models.DecimalField(
        _("reserved quantity"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )

    minimum_stock = models.DecimalField(
        _("minimum stock"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )
    reorder_threshold = models.DecimalField(
        _("reorder threshold"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )

    track_stock = models.BooleanField(
        _("track stock"),
        default=True,
        help_text=_("Turn off for made-to-order items such as fresh bakery batches."),
    )
    location = models.CharField(_("location"), max_length=64, blank=True)

    class Meta:
        verbose_name = _("inventory item")
        verbose_name_plural = _("inventory items")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__gte=0), name="inventory_reserved_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "quantity"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.product}: {self.available_quantity}"

    @property
    def available_quantity(self) -> Decimal:
        """What a new order may take. Never negative in the eyes of a customer."""
        available = self.quantity - self.reserved_quantity
        return available if available > 0 else Decimal("0.000")

    @property
    def is_low_stock(self) -> bool:
        return self.track_stock and self.available_quantity <= self.reorder_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.track_stock and self.available_quantity <= 0


class StockMovement(TenantOwnedModel):
    """One immutable change to a stock level.

    ``quantity`` is signed: positive adds, negative removes. ``balance_after``
    is the resulting physical quantity, captured at write time so a ledger can
    be reconciled without replaying every row.
    """

    inventory_item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="movements", verbose_name=_("item")
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="stock_movements"
    )
    movement_type = models.CharField(_("type"), max_length=16, choices=MovementType.choices)
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(
        _("balance after"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )

    reference_type = models.CharField(_("reference type"), max_length=32, blank=True)
    reference_id = models.CharField(_("reference id"), max_length=64, blank=True, db_index=True)
    note = models.CharField(_("note"), max_length=255, blank=True)

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("stock movement")
        verbose_name_plural = _("stock movements")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "product", "-created_at"]),
            models.Index(fields=["tenant", "movement_type", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.movement_type} {self.quantity} of {self.product}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Movements are write-once."""
        if self.pk and not self._state.adding:
            raise ValueError("Stock movements are immutable.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class StockReservation(TenantOwnedModel):
    """A temporary hold placed at checkout.

    Held stock stays physically present but is unavailable to other customers.
    On payment it is *committed* (physical quantity drops); on cancellation or
    expiry it is *released*.
    """

    inventory_item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="reservations"
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="reservations"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_reservations",
    )
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3)
    status = models.CharField(
        _("status"),
        max_length=12,
        choices=ReservationStatus.choices,
        default=ReservationStatus.HELD,
    )
    expires_at = models.DateTimeField(_("expires at"), db_index=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    class Meta:
        verbose_name = _("stock reservation")
        verbose_name_plural = _("stock reservations")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="reservation_quantity_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["tenant", "order"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.quantity} × {self.product} ({self.status})"

    @property
    def is_expired(self) -> bool:
        return self.status == ReservationStatus.HELD and self.expires_at <= timezone.now()
