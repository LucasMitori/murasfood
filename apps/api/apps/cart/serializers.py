"""Cart serializers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.catalog.serializers import ProductListSerializer
from apps.common.serializers import QuantitySerializerField

from .models import Cart, CartItem, ShoppingList, ShoppingListItem


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


# =============================================================================
# Shopping lists
# =============================================================================
class ShoppingListItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShoppingListItem
        fields = ["id", "product", "quantity", "unit_price", "line_total", "is_available", "note"]
        read_only_fields = ["id", "unit_price", "line_total", "is_available"]

    def get_unit_price(self, obj: ShoppingListItem) -> str:
        return str(obj.unit_price)

    def get_line_total(self, obj: ShoppingListItem) -> str:
        return str(obj.line_total)


class ShoppingListSerializer(serializers.ModelSerializer):
    """A list with its lines. Totals are computed on read, never stored."""

    items = ShoppingListItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()
    estimated_total = serializers.SerializerMethodField()

    class Meta:
        model = ShoppingList
        fields = ["id", "name", "note", "items", "item_count", "estimated_total", "updated_at"]
        read_only_fields = ["id", "items", "item_count", "estimated_total", "updated_at"]

    def get_item_count(self, obj: ShoppingList) -> int:
        return len(obj.items.all())

    def get_estimated_total(self, obj: ShoppingList) -> str:
        """What the list would cost at today's prices.

        "Estimated" is not hedging: prices move, and some lines may be
        unavailable when the list is finally used.
        """
        from apps.common.money import money_str

        return money_str(sum((item.line_total for item in obj.items.all()), Decimal("0.00")))


class ShoppingListSummarySerializer(serializers.ModelSerializer):
    """The list index, without dragging every line into the response."""

    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShoppingList
        fields = ["id", "name", "note", "item_count", "updated_at"]
        read_only_fields = fields


class ShoppingListWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ShoppingListItemWriteSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = QuantitySerializerField(required=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SaveCartAsListSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
