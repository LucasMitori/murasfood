"""Payment serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .models import Payment, PaymentEvent, PaymentRefund


class PaymentPublicSerializer(serializers.ModelSerializer):
    """What the paying customer sees.

    Includes the PIX payload and QR image; excludes provider metadata, fees and
    anything else that is the merchant's business rather than the payer's.
    """

    is_expired = serializers.BooleanField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "status",
            "status_label",
            "amount",
            "currency",
            "pix_payload",
            "pix_qr_code",
            "expires_at",
            "paid_at",
            "is_expired",
            "created_at",
        ]
        read_only_fields = fields


class PaymentAdminSerializer(serializers.ModelSerializer):
    """Merchant view, including provider references and fees."""

    order_number = serializers.CharField(source="order.number", read_only=True)
    refundable_amount = serializers.SerializerMethodField()
    net_amount = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_number",
            "provider",
            "external_id",
            "method",
            "status",
            "amount",
            "refunded_amount",
            "refundable_amount",
            "fee_amount",
            "net_amount",
            "currency",
            "pix_transaction_id",
            "expires_at",
            "paid_at",
            "failure_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_refundable_amount(self, obj: Payment) -> str:
        return str(obj.refundable_amount)

    def get_net_amount(self, obj: Payment) -> str:
        return str(obj.net_amount)


class PaymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentEvent
        fields = [
            "id",
            "provider",
            "provider_event_id",
            "event_type",
            "signature_valid",
            "processing_status",
            "processing_error",
            "processed_at",
            "created_at",
        ]
        read_only_fields = fields


class PaymentRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRefund
        fields = [
            "id",
            "payment",
            "amount",
            "status",
            "external_id",
            "reason",
            "requested_by",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class CreatePaymentSerializer(serializers.Serializer):
    order = serializers.UUIDField()
    method = serializers.CharField(max_length=16, required=False, default="PIX")


class RefundRequestSerializer(serializers.Serializer):
    amount = MoneySerializerField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
