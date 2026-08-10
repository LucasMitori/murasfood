"""Cart serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.catalog.serializers import ProductListSerializer
from apps.common.serializers import QuantitySerializerField

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    unit_price = serializers.SerializerMethodField()
    base_unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "base_unit_price",
            "line_total",
            "is_available",
            "note",
        ]
        read_only_fields = ["id", "unit_price", "base_unit_price", "line_total", "is_available"]

    def get_unit_price(self, obj: CartItem) -> str:
        return str(obj.unit_price)

    def get_base_unit_price(self, obj: CartItem) -> str:
        return str(obj.base_unit_price)

    def get_line_total(self, obj: CartItem) -> str:
        return str(obj.line_total)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()
    issues = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "token", "status", "coupon_code", "items", "totals", "issues", "updated_at"]
        read_only_fields = fields

    def get_totals(self, obj: Cart) -> dict[str, Any]:
        from .selectors import cart_totals

        request = self.context.get("request")
        params = getattr(request, "query_params", {}) if request else {}
        return cart_totals(
            obj,
            coupon_code=obj.coupon_code,
            delivery_method=params.get("delivery_method"),
            postal_code=params.get("postal_code", ""),
        )

    def get_issues(self, obj: Cart) -> list[dict[str, Any]]:
        from .selectors import unavailable_items

        return unavailable_items(obj)


class AddItemSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = QuantitySerializerField(required=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class UpdateItemSerializer(serializers.Serializer):
    quantity = QuantitySerializerField()


class ApplyCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
