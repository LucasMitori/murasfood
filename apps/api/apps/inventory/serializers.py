"""Inventory serializers."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.common.serializers import QuantitySerializerField

from .models import InventoryItem, RestockAlert, StockBatch, StockMovement, StockReservation


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


class StockBatchSerializer(serializers.ModelSerializer):
    """One lot of a product, with the date it stops being sellable."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit = serializers.CharField(source="product.sale_unit.code", read_only=True)

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    write_off_value = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )

    class Meta:
        model = StockBatch
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit",
            "code",
            "quantity",
            "expiry_date",
            "received_date",
            "supplier",
            "cost_price",
            "note",
            "days_remaining",
            "is_expired",
            "write_off_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        """A lot cannot expire before it arrived.

        Caught here rather than by a database constraint because the message
        belongs on the field the operator just typed, and because a partial
        update has to compare the new value against the stored one.
        """
        expiry = attrs.get("expiry_date") or getattr(self.instance, "expiry_date", None)
        received = attrs.get("received_date") or getattr(self.instance, "received_date", None)

        if expiry and received and expiry < received:
            raise serializers.ValidationError(
                {"expiry_date": _("An expiry date cannot fall before the date received.")}
            )

        return attrs


class RestockAlertRequestSerializer(serializers.Serializer):
    """Ask to be told when a product is back.

    ``email`` is optional for a signed-in customer — their account address is
    authoritative and letting them type a different one would turn the feature
    into an open relay for sending mail to arbitrary strangers.
    """

    email = serializers.EmailField(required=False, allow_blank=True)
    locale = serializers.CharField(max_length=10, required=False, allow_blank=True)


class RestockAlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = RestockAlert
        fields = [
            "id",
            "product",
            "product_name",
            "product_slug",
            "notified_at",
            "created_at",
        ]
        read_only_fields = fields


class RestockDemandSerializer(serializers.Serializer):
    """One row of the "what should I reorder" report."""

    product_id = serializers.CharField()
    name = serializers.CharField()
    sku = serializers.CharField()
    slug = serializers.CharField()
    waiting = serializers.IntegerField()
    latest_request = serializers.DateTimeField(allow_null=True)
