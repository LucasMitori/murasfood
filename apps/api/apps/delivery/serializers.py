"""Delivery serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .models import DeliverySettings, DeliveryZone


class DeliverySettingsSerializer(serializers.ModelSerializer):
    minimum_order_amount = MoneySerializerField(required=False)
    base_fee = MoneySerializerField(required=False)
    free_delivery_threshold = MoneySerializerField(required=False, allow_null=True)

    class Meta:
        model = DeliverySettings
        fields = [
            "delivery_enabled",
            "pickup_enabled",
            "minimum_order_amount",
            "base_fee",
            "free_delivery_threshold",
            "service_radius_km",
            "estimated_delivery_minutes",
            "estimated_pickup_minutes",
            "delivery_cutoff_minutes",
        ]


class DeliveryZoneSerializer(serializers.ModelSerializer):
    fee = MoneySerializerField()
    minimum_order_amount = MoneySerializerField(required=False)
    free_delivery_threshold = MoneySerializerField(required=False, allow_null=True)

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "postal_code_start",
            "postal_code_end",
            "fee",
            "minimum_order_amount",
            "free_delivery_threshold",
            "estimated_minutes",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("postal_code_start", getattr(self.instance, "postal_code_start", ""))
        end = attrs.get("postal_code_end", getattr(self.instance, "postal_code_end", ""))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"postal_code_end": "The end of the range must not precede its start."}
            )
        return attrs


class DeliveryQuoteRequestSerializer(serializers.Serializer):
    postal_code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    subtotal = MoneySerializerField(required=False)
