"""Order serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .constants import next_statuses
from .models import Order, OrderAddress, OrderItem, OrderNote, OrderStatusHistory


class OrderItemSerializer(serializers.ModelSerializer):
    """Line items as recorded, not as the catalog looks today."""

    product_slug = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_slug",
            "product_name",
            "product_sku",
            "unit_code",
            "quantity",
            "unit_price",
            "base_unit_price",
            "discount_amount",
            "line_total",
            "note",
            "image",
        ]
        read_only_fields = fields

    def get_product_slug(self, obj: OrderItem) -> str | None:
        return obj.product.slug if obj.product_id and obj.product else None

    def get_image(self, obj: OrderItem) -> dict[str, Any] | None:
        if not obj.product_id or obj.product is None:
            return None
        image = obj.product.primary_image
        if image is None:
            return None
        from apps.media.serializers import MediaAssetSerializer

        return MediaAssetSerializer(image.asset).data


class OrderItemAdminSerializer(OrderItemSerializer):
    """Adds the cost snapshot, which customers must never see."""

    margin = serializers.SerializerMethodField()

    class Meta(OrderItemSerializer.Meta):
        fields = [*OrderItemSerializer.Meta.fields, "unit_cost", "margin", "category_name"]

    def get_margin(self, obj: OrderItem) -> str | None:
        margin = obj.margin
        return str(margin) if margin is not None else None


class OrderAddressSerializer(serializers.ModelSerializer):
    one_line = serializers.CharField(read_only=True)

    class Meta:
        model = OrderAddress
        fields = [
            "recipient_name",
            "postal_code",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "country",
            "reference",
            "one_line",
        ]
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["id", "old_status", "new_status", "actor_label", "reason", "created_at"]
        read_only_fields = fields


class OrderNoteSerializer(serializers.ModelSerializer):
    author_label = serializers.SerializerMethodField()

    class Meta:
        model = OrderNote
        fields = ["id", "body", "is_customer_visible", "author", "author_label", "created_at"]
        read_only_fields = ["id", "author", "author_label", "created_at"]

    def get_author_label(self, obj: OrderNote) -> str:
        return obj.author.get_full_name() if obj.author else "system"


class OrderListSerializer(serializers.ModelSerializer):
    """Row in the customer's or merchant's order list."""

    item_count = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "status_label",
            "delivery_method",
            "total",
            "currency",
            "item_count",
            "placed_at",
            "created_at",
        ]
        read_only_fields = fields


class OrderDetailSerializer(serializers.ModelSerializer):
    """The customer's view of one order."""

    items = OrderItemSerializer(many=True, read_only=True)
    address = OrderAddressSerializer(read_only=True)
    timeline = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    can_cancel = serializers.BooleanField(source="is_cancellable_by_customer", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "status_label",
            "delivery_method",
            "currency",
            "subtotal",
            "discount_total",
            "delivery_fee",
            "tax_total",
            "total",
            "refunded_total",
            "coupon_code",
            "customer_note",
            "items",
            "address",
            "timeline",
            "payment",
            "can_cancel",
            "scheduled_for",
            "estimated_ready_at",
            "placed_at",
            "paid_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_timeline(self, obj: Order) -> list[dict[str, Any]]:
        from .selectors import order_timeline

        return order_timeline(obj)

    def get_payment(self, obj: Order) -> dict[str, Any] | None:
        """The payment the customer should act on, if any."""
        from apps.payments.serializers import PaymentPublicSerializer

        payment = obj.payments.order_by("-created_at").first()
        return PaymentPublicSerializer(payment).data if payment else None


class OrderAdminSerializer(OrderDetailSerializer):
    """Merchant view: costs, internal notes, full history, allowed next steps."""

    items = OrderItemAdminSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    notes = OrderNoteSerializer(many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()
    cost_total = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(read_only=True)

    class Meta(OrderDetailSerializer.Meta):
        fields = [
            *OrderDetailSerializer.Meta.fields,
            "customer",
            "customer_name",
            "customer_email",
            "customer_phone",
            "internal_note",
            "cancellation_reason",
            "status_history",
            "notes",
            "allowed_transitions",
            "cost_total",
        ]

    def get_allowed_transitions(self, obj: Order) -> list[str]:
        return list(next_statuses(obj.status))

    def get_cost_total(self, obj: Order) -> str:
        return str(obj.cost_total)


class CheckoutSerializer(serializers.Serializer):
    """Checkout input.

    Notably absent: any monetary field. Prices, discounts and delivery fees are
    computed server-side (invariant #2).
    """

    delivery_method = serializers.ChoiceField(choices=["PICKUP", "DELIVERY"])
    address = serializers.UUIDField(required=False, allow_null=True)
    customer_note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    payment_method = serializers.CharField(required=False, default="PIX")

    contact_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    contact_email = serializers.EmailField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["delivery_method"] == "DELIVERY" and not attrs.get("address"):
            raise serializers.ValidationError(
                {"address": "A delivery address is required for delivery orders."}
            )
        return attrs


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=24)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RefundSerializer(serializers.Serializer):
    amount = MoneySerializerField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
