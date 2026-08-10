"""Promotion serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .models import Coupon, CouponRedemption, DiscountType, Promotion


class PromotionSerializer(serializers.ModelSerializer):
    value = MoneySerializerField()
    minimum_order_amount = MoneySerializerField(required=False)
    max_discount_amount = MoneySerializerField(required=False, allow_null=True)
    is_running = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            "id",
            "name",
            "description",
            "discount_type",
            "scope",
            "value",
            "max_discount_amount",
            "buy_quantity",
            "get_quantity",
            "minimum_order_amount",
            "products",
            "categories",
            "starts_at",
            "ends_at",
            "usage_limit",
            "usage_count",
            "per_customer_limit",
            "requires_coupon",
            "is_stackable",
            "priority",
            "is_active",
            "is_running",
            "created_at",
        ]
        read_only_fields = ["id", "usage_count", "is_running", "created_at"]

    def get_is_running(self, obj: Promotion) -> bool:
        return obj.is_running()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        discount_type = attrs.get("discount_type", getattr(self.instance, "discount_type", None))
        value = attrs.get("value", getattr(self.instance, "value", None))

        if discount_type == DiscountType.PERCENTAGE and value is not None and value > 100:
            raise serializers.ValidationError({"value": "A percentage cannot exceed 100."})

        if discount_type == DiscountType.BUY_X_GET_Y:
            buy = attrs.get("buy_quantity", getattr(self.instance, "buy_quantity", 0))
            get = attrs.get("get_quantity", getattr(self.instance, "get_quantity", 0))
            if buy <= 0 or get <= 0:
                raise serializers.ValidationError(
                    {"buy_quantity": "Buy and get quantities must both be greater than zero."}
                )
        return attrs


class PromotionPublicSerializer(serializers.ModelSerializer):
    """What the storefront may show about a running promotion."""

    class Meta:
        model = Promotion
        fields = ["id", "name", "description", "discount_type", "value", "minimum_order_amount"]
        read_only_fields = fields


class CouponSerializer(serializers.ModelSerializer):
    promotion_name = serializers.CharField(source="promotion.name", read_only=True)
    is_redeemable = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "promotion",
            "promotion_name",
            "max_uses",
            "max_uses_per_customer",
            "used_count",
            "starts_at",
            "ends_at",
            "is_active",
            "is_redeemable",
            "created_at",
        ]
        read_only_fields = ["id", "used_count", "is_redeemable", "created_at"]

    def get_is_redeemable(self, obj: Coupon) -> bool:
        return obj.is_redeemable()


class CouponRedemptionSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source="coupon.code", read_only=True)

    class Meta:
        model = CouponRedemption
        fields = [
            "id",
            "coupon",
            "coupon_code",
            "customer",
            "order",
            "discount_amount",
            "created_at",
        ]
        read_only_fields = fields


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
