"""
Pricing models.

Price is deliberately separate from :class:`~apps.catalog.models.Product`
(spec §13). A product has *many* prices over time and by quantity tier; the
current one is a query, not a column.

Two invariants are enforced here:

* **History is append-only.** ``PriceHistory`` rows are never updated or
  deleted, so "what did this cost in March?" always has an answer
  (invariant #10).
* **Money is ``Decimal``.** Every monetary column is ``DecimalField``; nothing
  in this module ever touches a float (invariant #14).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class PriceChangeReason(models.TextChoices):
    INITIAL = "INITIAL", _("Initial price")
    MANUAL = "MANUAL", _("Manual change")
    PROMOTION = "PROMOTION", _("Promotion")
    COST_CHANGE = "COST_CHANGE", _("Cost change")
    SCHEDULED = "SCHEDULED", _("Scheduled change")
    IMPORT = "IMPORT", _("Bulk import")


class PriceList(TenantOwnedModel):
    """A named set of prices.

    The MVP uses a single default list per tenant. The model exists so customer
    groups ("wholesale") and per-branch pricing can be added later without a
    migration that touches every price row (spec §64).
    """

    name = models.CharField(_("name"), max_length=120)
    code = models.SlugField(_("code"), max_length=64)
    is_default = models.BooleanField(_("default"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("price list")
        verbose_name_plural = _("price lists")
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_price_list_tenant_code"),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_default=True),
                name="uniq_default_price_list_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProductPrice(TenantOwnedModel):
    """The price of a product, optionally scheduled and quantity-tiered.

    ``min_quantity`` implements "buy 3 or more and pay less": the row with the
    highest ``min_quantity`` not exceeding the ordered quantity wins.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="prices",
        verbose_name=_("product"),
    )
    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name="prices",
        null=True,
        blank=True,
        verbose_name=_("price list"),
    )

    base_price = models.DecimalField(
        _("base price"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    sale_price = models.DecimalField(
        _("promotional price"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("When set and within the schedule, this is what the customer pays."),
    )
    cost_price = models.DecimalField(
        _("cost"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Used for margin analysis. Never shown to customers."),
    )

    min_quantity = models.DecimalField(
        _("minimum quantity"),
        max_digits=10,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    starts_at = models.DateTimeField(_("valid from"), null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(_("valid until"), null=True, blank=True, db_index=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("product price")
        verbose_name_plural = _("product prices")
        ordering = ["-min_quantity", "-starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_price__gte=0), name="price_base_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(sale_price__isnull=True) | models.Q(sale_price__gte=0),
                name="price_sale_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(starts_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="price_window_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "is_active"]),
            models.Index(fields=["product", "min_quantity", "is_active"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.product}: {self.effective_price}"

    @property
    def effective_price(self) -> Decimal:
        """Sale price when present, otherwise the base price.

        Schedule validity is *not* checked here — use
        :func:`apps.pricing.selectors.resolve_price`, which filters by window in
        SQL. This property is for display on an already-selected row.
        """
        return self.sale_price if self.sale_price is not None else self.base_price

    @property
    def is_discounted(self) -> bool:
        return self.sale_price is not None and self.sale_price < self.base_price


class PriceHistory(TenantOwnedModel):
    """Append-only record of every price change (spec §13).

    Never updated, never deleted. ``old_value``/``new_value`` are nullable so
    the very first price and a deletion both have a representation.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="price_history",
        verbose_name=_("product"),
    )
    price = models.ForeignKey(
        ProductPrice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history",
        verbose_name=_("price row"),
    )
    field = models.CharField(_("field"), max_length=32, default="base_price")
    old_value = models.DecimalField(
        _("previous value"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    new_value = models.DecimalField(
        _("new value"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    reason = models.CharField(
        _("reason"),
        max_length=20,
        choices=PriceChangeReason.choices,
        default=PriceChangeReason.MANUAL,
    )
    note = models.CharField(_("note"), max_length=255, blank=True)
    changed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("price history")
        verbose_name_plural = _("price history")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "product", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.product} {self.field}: {self.old_value} → {self.new_value}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Reject updates: historical prices cannot be rewritten."""
        if self.pk and not self._state.adding:
            raise ValueError("Price history is immutable.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @property
    def variation(self) -> Decimal | None:
        """Absolute change, or ``None`` when there was no previous value."""
        if self.old_value is None or self.new_value is None:
            return None
        return self.new_value - self.old_value
