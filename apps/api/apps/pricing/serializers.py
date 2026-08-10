"""Pricing serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField, QuantitySerializerField

from .models import PriceHistory, PriceList, ProductPrice


class PriceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceList
        fields = ["id", "name", "code", "is_default", "is_active"]
        read_only_fields = ["id"]


class ProductPriceSerializer(serializers.ModelSerializer):
    base_price = MoneySerializerField()
    sale_price = MoneySerializerField(required=False, allow_null=True)
    cost_price = MoneySerializerField(required=False, allow_null=True)
    min_quantity = QuantitySerializerField(required=False)
    effective_price = serializers.SerializerMethodField()
    is_discounted = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductPrice
        fields = [
            "id",
            "product",
            "base_price",
            "sale_price",
            "cost_price",
            "effective_price",
            "is_discounted",
            "min_quantity",
            "starts_at",
            "ends_at",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "effective_price", "is_discounted", "created_at"]

    def get_effective_price(self, obj: ProductPrice) -> str:
        return str(obj.effective_price)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        base = attrs.get("base_price", getattr(self.instance, "base_price", None))
        sale = attrs.get("sale_price", getattr(self.instance, "sale_price", None))
        if base is not None and sale is not None and sale > base:
            raise serializers.ValidationError(
                {"sale_price": "The promotional price cannot exceed the base price."}
            )
        return attrs


class PriceWriteSerializer(serializers.Serializer):
    """Input for the "set the price of this product" operation."""

    product = serializers.UUIDField()
    base_price = MoneySerializerField()
    sale_price = MoneySerializerField(required=False, allow_null=True)
    cost_price = MoneySerializerField(required=False, allow_null=True)
    min_quantity = QuantitySerializerField(required=False)
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, default="MANUAL")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PriceHistorySerializer(serializers.ModelSerializer):
    changed_by_label = serializers.SerializerMethodField()
    variation = serializers.SerializerMethodField()

    class Meta:
        model = PriceHistory
        fields = [
            "id",
            "product",
            "field",
            "old_value",
            "new_value",
            "variation",
            "reason",
            "note",
            "changed_by",
            "changed_by_label",
            "created_at",
        ]
        read_only_fields = fields

    def get_changed_by_label(self, obj: PriceHistory) -> str:
        return obj.changed_by.get_full_name() if obj.changed_by else "system"

    def get_variation(self, obj: PriceHistory) -> str | None:
        variation = obj.variation
        return str(variation) if variation is not None else None


class MarginAnalysisSerializer(serializers.Serializer):
    """Read model for the pricing analytics table."""

    product_id = serializers.UUIDField()
    product_name = serializers.CharField()
    sku = serializers.CharField()
    cost_price = serializers.CharField(allow_null=True)
    sale_price = serializers.CharField()
    gross_margin = serializers.CharField(allow_null=True)
    gross_margin_percentage = serializers.CharField(allow_null=True)
    markup_percentage = serializers.CharField(allow_null=True)
    units_sold = serializers.IntegerField()
    revenue = serializers.CharField()
