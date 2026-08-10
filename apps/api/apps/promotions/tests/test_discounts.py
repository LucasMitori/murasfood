"""
The discount engine.

Discounts are computed server-side and can never exceed the subtotal
(spec §23).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.promotions.models import Coupon, CouponRedemption, DiscountType, Promotion, PromotionScope
from apps.promotions.services import (
    CartLine,
    CouponError,
    calculate_discounts,
    redeem_coupon,
    validate_coupon,
)

pytestmark = pytest.mark.django_db


def line(product: Any, *, quantity: str = "1", price: str = "10.00") -> CartLine:
    return CartLine(
        product_id=product.pk,
        category_id=product.category_id,
        quantity=Decimal(quantity),
        unit_price=Decimal(price),
    )


class TestPercentageDiscounts:
    def test_applies_to_the_whole_order(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="10% off",
            discount_type=DiscountType.PERCENTAGE,
            scope=PromotionScope.ORDER,
            value=Decimal("10.00"),
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="2")], subtotal=Decimal("20.00")
        )
        assert result.total_discount == Decimal("2.00")

    def test_respects_the_discount_ceiling(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="20% capped at 5",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("20.00"),
            max_discount_amount=Decimal("5.00"),
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="10")], subtotal=Decimal("100.00")
        )
        assert result.total_discount == Decimal("5.00")

    def test_minimum_order_is_enforced(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="10% acima de 50",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            minimum_order_amount=Decimal("50.00"),
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product)], subtotal=Decimal("10.00")
        )
        assert result.total_discount == Decimal("0.00")


class TestFixedAndScoped:
    def test_fixed_discount_never_exceeds_the_subtotal(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="R$50 off",
            discount_type=DiscountType.FIXED,
            value=Decimal("50.00"),
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product)], subtotal=Decimal("10.00")
        )
        assert result.total_discount == Decimal("10.00")

    def test_category_scope_only_touches_matching_lines(
        self, tenant: Any, category: Any, unit: Any, product: Any
    ) -> None:
        from apps.catalog.models import Category
        from conftest import make_product

        other_category = Category.objects.create(tenant=tenant, name="Bebidas", slug="bebidas")
        other = make_product(
            tenant=tenant, category=other_category, unit=unit, name="Suco", price="10.00"
        )

        promotion = Promotion.objects.create(
            tenant=tenant,
            name="20% na mercearia",
            discount_type=DiscountType.PERCENTAGE,
            scope=PromotionScope.CATEGORY,
            value=Decimal("20.00"),
        )
        promotion.categories.add(category)

        result = calculate_discounts(
            tenant=tenant,
            lines=[line(product, price="10.00"), line(other, price="10.00")],
            subtotal=Decimal("20.00"),
        )
        assert result.total_discount == Decimal("2.00")

    def test_buy_two_get_one_discounts_the_cheapest_unit(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="Leve 3 pague 2",
            discount_type=DiscountType.BUY_X_GET_Y,
            buy_quantity=2,
            get_quantity=1,
        )

        result = calculate_discounts(
            tenant=tenant,
            lines=[line(product, quantity="3", price="10.00")],
            subtotal=Decimal("30.00"),
        )
        assert result.total_discount == Decimal("10.00")


class TestStacking:
    def test_non_stackable_promotions_do_not_combine(self, tenant: Any, product: Any) -> None:
        """Only the best exclusive promotion applies."""
        Promotion.objects.create(
            tenant=tenant,
            name="10%",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
        )
        Promotion.objects.create(
            tenant=tenant,
            name="20%",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("20.00"),
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="10")], subtotal=Decimal("100.00")
        )
        assert result.total_discount == Decimal("20.00")
        assert len(result.lines) == 1

    def test_free_delivery_stacks_with_a_discount(self, tenant: Any, product: Any) -> None:
        Promotion.objects.create(
            tenant=tenant,
            name="10%",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
        )
        Promotion.objects.create(
            tenant=tenant,
            name="Frete grátis",
            discount_type=DiscountType.FREE_DELIVERY,
            is_stackable=True,
        )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="10")], subtotal=Decimal("100.00")
        )
        assert result.total_discount == Decimal("10.00")
        assert result.free_delivery is True

    def test_total_discount_is_capped_at_the_subtotal(self, tenant: Any, product: Any) -> None:
        """An order can never go negative."""
        for index in range(3):
            Promotion.objects.create(
                tenant=tenant,
                name=f"Cumulativo {index}",
                discount_type=DiscountType.PERCENTAGE,
                value=Decimal("60.00"),
                is_stackable=True,
            )

        result = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="10")], subtotal=Decimal("100.00")
        )
        assert result.total_discount == Decimal("100.00")


class TestCoupons:
    @pytest.fixture
    def coupon(self, tenant: Any) -> Coupon:
        promotion = Promotion.objects.create(
            tenant=tenant,
            name="Cupom 15%",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("15.00"),
            requires_coupon=True,
        )
        return Coupon.objects.create(
            tenant=tenant, promotion=promotion, code="promo15", max_uses_per_customer=1
        )

    def test_code_is_stored_uppercase(self, coupon: Coupon) -> None:
        assert coupon.code == "PROMO15"

    def test_coupon_only_applies_when_supplied(
        self, tenant: Any, product: Any, coupon: Coupon
    ) -> None:
        without = calculate_discounts(
            tenant=tenant, lines=[line(product, quantity="10")], subtotal=Decimal("100.00")
        )
        assert without.total_discount == Decimal("0.00")

        with_code = calculate_discounts(
            tenant=tenant,
            lines=[line(product, quantity="10")],
            subtotal=Decimal("100.00"),
            coupon_code="promo15",
        )
        assert with_code.total_discount == Decimal("15.00")

    def test_unknown_code_is_rejected(self, tenant: Any, customer: Any) -> None:
        with pytest.raises(CouponError) as exc:
            validate_coupon(
                tenant=tenant, code="NOPE", customer=customer, subtotal=Decimal("100.00")
            )
        assert exc.value.default_code == "COUPON_NOT_FOUND"

    def test_expired_coupon_is_rejected(self, tenant: Any, customer: Any, coupon: Coupon) -> None:
        coupon.ends_at = timezone.now() - timedelta(days=1)
        coupon.save()

        with pytest.raises(CouponError):
            validate_coupon(
                tenant=tenant, code=coupon.code, customer=customer, subtotal=Decimal("100.00")
            )

    def test_per_customer_limit_is_enforced(
        self, tenant: Any, customer: Any, coupon: Coupon, filled_cart: Any
    ) -> None:
        from apps.orders.services import create_order_from_cart

        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )
        redeem_coupon(coupon=coupon, order=order, discount_amount=Decimal("5.00"))

        with pytest.raises(CouponError) as exc:
            validate_coupon(
                tenant=tenant, code=coupon.code, customer=customer, subtotal=Decimal("100.00")
            )
        assert exc.value.default_code == "COUPON_ALREADY_USED"

    def test_redemption_is_idempotent_per_order(
        self, tenant: Any, customer: Any, coupon: Coupon, filled_cart: Any
    ) -> None:
        """A retried checkout must not burn a single-use coupon twice."""
        from apps.orders.services import create_order_from_cart

        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )
        redeem_coupon(coupon=coupon, order=order, discount_amount=Decimal("5.00"))
        redeem_coupon(coupon=coupon, order=order, discount_amount=Decimal("5.00"))

        coupon.refresh_from_db()
        assert coupon.used_count == 1
        assert CouponRedemption.objects.filter(coupon=coupon, order=order).count() == 1
