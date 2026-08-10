"""
Promotion and coupon models.

Discounts are *never* accepted from the client (spec §23). The frontend may show
a preview, but the amount that reaches an order is always recomputed here from
the promotion rules that were active at that moment.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class DiscountType(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", _("Percentage off")
    FIXED = "FIXED", _("Fixed amount off")
    FREE_DELIVERY = "FREE_DELIVERY", _("Free delivery")
    BUY_X_GET_Y = "BUY_X_GET_Y", _("Buy X get Y")


class PromotionScope(models.TextChoices):
    ORDER = "ORDER", _("Whole order")
    PRODUCT = "PRODUCT", _("Selected products")
    CATEGORY = "CATEGORY", _("Selected categories")


class Promotion(TenantOwnedModel):
    """A discount rule."""

    name = models.CharField(_("name"), max_length=160)
    description = models.TextField(_("description"), blank=True)

    discount_type = models.CharField(
        _("discount type"), max_length=16, choices=DiscountType.choices
    )
    scope = models.CharField(
        _("scope"), max_length=16, choices=PromotionScope.choices, default=PromotionScope.ORDER
    )
    value = models.DecimalField(
        _("value"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Percentage (0–100) or a currency amount, depending on the type."),
    )
    max_discount_amount = models.DecimalField(
        _("discount ceiling"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Caps a percentage discount, e.g. 20% off up to R$30."),
    )

    # Buy X get Y
    buy_quantity = models.PositiveSmallIntegerField(_("buy quantity"), default=0)
    get_quantity = models.PositiveSmallIntegerField(_("free quantity"), default=0)

    minimum_order_amount = models.DecimalField(
        _("minimum order"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    products = models.ManyToManyField(
        "catalog.Product", blank=True, related_name="promotions", verbose_name=_("products")
    )
    categories = models.ManyToManyField(
        "catalog.Category", blank=True, related_name="promotions", verbose_name=_("categories")
    )

    starts_at = models.DateTimeField(_("starts at"), null=True, blank=True)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True)

    usage_limit = models.PositiveIntegerField(
        _("total usage limit"), null=True, blank=True, help_text=_("Blank means unlimited.")
    )
    usage_count = models.PositiveIntegerField(_("times used"), default=0)
    per_customer_limit = models.PositiveIntegerField(_("per-customer limit"), null=True, blank=True)

    requires_coupon = models.BooleanField(
        _("requires a coupon code"),
        default=False,
        help_text=_("When off, the promotion applies automatically."),
    )
    is_stackable = models.BooleanField(
        _("stackable"),
        default=False,
        help_text=_("Whether it can combine with other promotions."),
    )
    priority = models.IntegerField(
        _("priority"), default=0, help_text=_("Higher priority is evaluated first.")
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("promotion")
        verbose_name_plural = _("promotions")
        ordering = ["-priority", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(value__gte=0), name="promotion_value_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(starts_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="promotion_window_ordered",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "is_active", "-priority"])]

    def __str__(self) -> str:
        return self.name

    def is_running(self, moment: object = None) -> bool:
        """Whether the promotion is live and has budget left."""
        now = moment or timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return not (self.usage_limit is not None and self.usage_count >= self.usage_limit)


class Coupon(TenantOwnedModel):
    """A redeemable code bound to a promotion.

    Codes are stored uppercase and matched case-insensitively — customers type
    them off a printed flyer.
    """

    promotion = models.ForeignKey(
        Promotion, on_delete=models.CASCADE, related_name="coupons", verbose_name=_("promotion")
    )
    code = models.CharField(_("code"), max_length=32)
    max_uses = models.PositiveIntegerField(_("maximum uses"), null=True, blank=True)
    max_uses_per_customer = models.PositiveIntegerField(_("maximum uses per customer"), default=1)
    used_count = models.PositiveIntegerField(_("times used"), default=0)
    starts_at = models.DateTimeField(_("starts at"), null=True, blank=True)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_coupon_tenant_code"),
        ]
        indexes = [models.Index(fields=["tenant", "code", "is_active"])]

    def __str__(self) -> str:
        return self.code

    def save(self, *args: object, **kwargs: object) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def is_redeemable(self, moment: object = None) -> bool:
        now = moment or timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return self.promotion.is_running(now)


class CouponRedemption(TenantOwnedModel):
    """One use of a coupon. Also the per-customer limit ledger."""

    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name="redemptions", verbose_name=_("coupon")
    )
    customer = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="coupon_redemptions"
    )
    discount_amount = models.DecimalField(_("discount"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("coupon redemption")
        verbose_name_plural = _("coupon redemptions")
        ordering = ["-created_at"]
        constraints = [
            # A coupon is recorded once per order; retrying checkout must not
            # inflate the usage counter.
            models.UniqueConstraint(
                fields=["coupon", "order"], name="uniq_redemption_coupon_order"
            ),
        ]
        indexes = [models.Index(fields=["coupon", "customer"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.coupon} → {self.discount_amount}"
