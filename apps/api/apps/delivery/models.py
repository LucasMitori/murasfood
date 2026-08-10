"""
Delivery models.

The MVP supports pickup and a fixed (optionally zone-based) delivery fee, with
free delivery above a threshold — what a neighbourhood market actually needs
(spec §20). Distance-based pricing and third-party couriers slot in behind the
same service interface later.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel


class DeliveryMethod(models.TextChoices):
    PICKUP = "PICKUP", _("Pick up in store")
    DELIVERY = "DELIVERY", _("Delivery")


class DeliverySettings(BaseModel):
    """Per-tenant delivery configuration."""

    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="delivery_settings",
        verbose_name=_("tenant"),
    )

    delivery_enabled = models.BooleanField(_("delivery enabled"), default=True)
    pickup_enabled = models.BooleanField(_("pickup enabled"), default=True)

    minimum_order_amount = models.DecimalField(
        _("minimum order"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    base_fee = models.DecimalField(
        _("delivery fee"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    free_delivery_threshold = models.DecimalField(
        _("free delivery from"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Orders at or above this subtotal ship free. Blank disables the rule."),
    )

    service_radius_km = models.DecimalField(
        _("service radius (km)"), max_digits=6, decimal_places=2, default=Decimal("5.00")
    )
    estimated_delivery_minutes = models.PositiveIntegerField(
        _("estimated delivery time (min)"), default=60
    )
    estimated_pickup_minutes = models.PositiveIntegerField(
        _("estimated preparation time (min)"), default=30
    )

    delivery_cutoff_minutes = models.PositiveIntegerField(
        _("cutoff before closing (min)"),
        default=30,
        help_text=_("Orders are refused this long before the store closes."),
    )

    class Meta:
        verbose_name = _("delivery settings")
        verbose_name_plural = _("delivery settings")

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.tenant} delivery"


class DeliveryZone(TenantOwnedModel):
    """A postal-code range with its own fee and estimate.

    Brazilian CEPs are contiguous numeric ranges per neighbourhood, so a
    start/end pair models a delivery area without any geo dependency.
    """

    name = models.CharField(_("name"), max_length=120)
    postal_code_start = models.CharField(_("CEP from"), max_length=8)
    postal_code_end = models.CharField(_("CEP to"), max_length=8)

    fee = models.DecimalField(_("fee"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    minimum_order_amount = models.DecimalField(
        _("minimum order"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    free_delivery_threshold = models.DecimalField(
        _("free delivery from"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    estimated_minutes = models.PositiveIntegerField(_("estimated time (min)"), default=60)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("delivery zone")
        verbose_name_plural = _("delivery zones")
        ordering = ["postal_code_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "postal_code_start", "postal_code_end"],
                name="uniq_zone_tenant_range",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.postal_code_start}–{self.postal_code_end})"

    def covers(self, postal_code: str) -> bool:
        """Whether a CEP falls inside this zone."""
        digits = "".join(ch for ch in postal_code if ch.isdigit())
        if len(digits) != 8:
            return False
        return self.postal_code_start <= digits <= self.postal_code_end
