"""Inventory serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import QuantitySerializerField

from .models import InventoryItem, StockMovement, StockReservation


class InventoryItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit = serializers.CharField(source="product.sale_unit.code", read_only=True)
    available_quantity = serializers.SerializerMethodField()
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit",
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "minimum_stock",
            "reorder_threshold",
            "track_stock",
            "location",
            "is_low_stock",
            "is_out_of_stock",
            "updated_at",
        ]
        read_only_fields = ["id", "quantity", "reserved_quantity", "updated_at"]

    def get_available_quantity(self, obj: InventoryItem) -> str:
        return str(obj.available_quantity)


class StockAdjustmentSerializer(serializers.Serializer):
    """Input for a manual stock change."""

    product = serializers.UUIDField()
    quantity_delta = QuantitySerializerField(
        min_value=None, help_text="Signed: positive receives stock, negative removes it."
    )
    movement_type = serializers.CharField(required=False, default="ADJUSTMENT")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class StockCountSerializer(serializers.Serializer):
    """Input for an absolute stock count."""

    product = serializers.UUIDField()
    quantity = QuantitySerializerField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    actor_label = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "product_name",
            "movement_type",
            "quantity",
            "balance_after",
            "reference_type",
            "reference_id",
            "note",
            "actor",
            "actor_label",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_label(self, obj: StockMovement) -> str:
        return obj.actor.get_full_name() if obj.actor else "system"


class StockReservationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockReservation
        fields = [
            "id",
            "product",
            "product_name",
            "order",
            "quantity",
            "status",
            "expires_at",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields
