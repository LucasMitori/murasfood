"""Order and checkout endpoints."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Address
from apps.common.exceptions import NotFoundError
from apps.common.idempotency import extract_key, run_idempotent
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import Order
from .selectors import orders_for_customer, search_orders
from .serializers import (
    CheckoutSerializer,
    OrderAdminSerializer,
    OrderCancelSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderNoteSerializer,
    OrderStatusUpdateSerializer,
    RefundSerializer,
)
from .services import (
    add_note,
    cancel_order,
    create_order_from_cart,
    register_refund,
    transition_order,
)


class CheckoutView(TenantScopedMixin, APIView):
    """Turn the caller's cart into an order and open a payment.

    Idempotent: send the same ``Idempotency-Key`` twice — a double-tapped
    button, a retried request after a timeout — and the second call returns the
    first order rather than creating another one (spec §49).
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "checkout"

    @extend_schema(
        request=CheckoutSerializer,
        responses={201: OrderDetailSerializer},
        operation_id="checkout_create",
    )
    def post(self, request: Request) -> Response:
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        status_code, body, replayed = run_idempotent(
            key=extract_key(request),
            scope="checkout",
            payload=request.data,
            tenant_id=self.tenant_id,
            user_id=request.user.pk,
            ttl_seconds=settings.IDEMPOTENCY_KEY_TTL_SECONDS,
            operation=lambda: self._checkout(request, data),
        )
        response = Response(body, status=status_code)
        if replayed:
            response["X-Idempotent-Replay"] = "true"
        return response

    def _checkout(self, request: Request, data: dict[str, Any]) -> tuple[int, Any]:
        from apps.cart.selectors import current_cart_for
        from apps.payments.services import create_payment_for_order

        cart = current_cart_for(request=request, tenant=self.tenant, create=False)
        if cart is None:
            from .services import EmptyCartError

            raise EmptyCartError()

        address = None
        if data.get("address"):
            address = Address.objects.filter(
                pk=data["address"], customer=request.user, tenant_id=self.tenant_id
            ).first()
            if address is None:
                raise NotFoundError(details={"field": "address"})

        order = create_order_from_cart(
            tenant=self.tenant,
            cart=cart,
            delivery_method=data["delivery_method"],
            address=address,
            customer=request.user,
            customer_note=data.get("customer_note", ""),
            scheduled_for=data.get("scheduled_for"),
            contact={
                "name": data.get("contact_name", ""),
                "email": data.get("contact_email", ""),
                "phone": data.get("contact_phone", ""),
            },
        )

        create_payment_for_order(order=order, method=data.get("payment_method", "PIX"))

        order = Order.objects.with_details().get(pk=order.pk)
        return http_status.HTTP_201_CREATED, OrderDetailSerializer(order).data


class OrderViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """The signed-in customer's own orders."""

    permission_classes = [IsAuthenticated]
    lookup_field = "number"
    lookup_value_regex = "[^/]+"

    def get_queryset(self) -> Any:
        return orders_for_customer(tenant_id=self.tenant_id, customer=self.request.user)

    def get_serializer_class(self) -> Any:
        return OrderDetailSerializer if self.action != "list" else OrderListSerializer

    @extend_schema(
        request=OrderCancelSerializer,
        responses=OrderDetailSerializer,
        operation_id="orders_cancel",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, number: str | None = None) -> Response:
        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = cancel_order(
            self.get_object(),
            actor=request.user,
            reason=serializer.validated_data["reason"] or _("Cancelled by the customer"),
            by_customer=True,
        )
        return Response(OrderDetailSerializer(Order.objects.with_details().get(pk=order.pk)).data)

    @extend_schema(responses={200: dict}, operation_id="orders_receipt")
    @action(detail=True, methods=["get"])
    def receipt(self, request: Request, number: str | None = None) -> Response:
        """Generate (or return) the PDF receipt for a paid order."""
        from apps.reports.services import generate_order_receipt

        order = self.get_object()
        document = generate_order_receipt(order)
        return Response(
            {
                "document_id": str(document.pk),
                "download_url": document.download_url,
                "filename": document.filename,
            }
        )


class OrderAdminFilter(filters.FilterSet):
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    delivery_method = filters.CharFilter(lookup_expr="iexact")
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    min_total = filters.NumberFilter(field_name="total", lookup_expr="gte")
    max_total = filters.NumberFilter(field_name="total", lookup_expr="lte")
    customer = filters.UUIDFilter(field_name="customer_id")

    class Meta:
        model = Order
        fields = ["status", "delivery_method", "customer"]


class AdminOrderViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Merchant order management.

    Read-only by design: orders change through explicit, audited transitions,
    never through a generic PATCH that could rewrite a total.
    """

    serializer_class = OrderAdminSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["orders.view"],
        "retrieve": ["orders.view"],
        "update_status": ["orders.update"],
        "cancel": ["orders.cancel"],
        "refund": ["orders.refund"],
        "add_note": ["orders.update"],
        "default": ["orders.view"],
    }
    filterset_class = OrderAdminFilter
    ordering_fields = ["created_at", "total", "status"]

    def get_queryset(self) -> Any:
        queryset = (
            Order.objects.for_tenant(self.tenant_id)
            .with_details()
            .prefetch_related("notes", "status_history")
            .order_by("-created_at")
        )
        return search_orders(queryset, self.request.query_params.get("q", ""))

    @extend_schema(
        request=OrderStatusUpdateSerializer,
        responses=OrderAdminSerializer,
        operation_id="admin_orders_update_status",
    )
    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request: Request, pk: str | None = None) -> Response:
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = transition_order(
            self.get_object(),
            to_status=serializer.validated_data["status"],
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(OrderAdminSerializer(Order.objects.with_details().get(pk=order.pk)).data)

    @extend_schema(
        request=OrderCancelSerializer,
        responses=OrderAdminSerializer,
        operation_id="admin_orders_cancel",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = cancel_order(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(OrderAdminSerializer(Order.objects.with_details().get(pk=order.pk)).data)

    @extend_schema(
        request=RefundSerializer,
        responses=OrderAdminSerializer,
        operation_id="admin_orders_refund",
    )
    @action(detail=True, methods=["post"])
    def refund(self, request: Request, pk: str | None = None) -> Response:
        """Refund through the payment provider, then record it on the order."""
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.payments.services import refund_order_payment

        order = self.get_object()
        amount = serializer.validated_data["amount"]
        reason = serializer.validated_data["reason"]

        refund_order_payment(order=order, amount=amount, actor=request.user, reason=reason)
        order = register_refund(order, amount=amount, actor=request.user, reason=reason)

        return Response(OrderAdminSerializer(Order.objects.with_details().get(pk=order.pk)).data)

    @extend_schema(
        request=OrderNoteSerializer,
        responses={201: OrderNoteSerializer},
        operation_id="admin_orders_add_note",
    )
    @action(detail=True, methods=["post"], url_path="notes")
    def add_note(self, request: Request, pk: str | None = None) -> Response:
        serializer = OrderNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        note = add_note(
            order=self.get_object(),
            author=request.user,
            body=serializer.validated_data["body"],
            customer_visible=serializer.validated_data.get("is_customer_visible", False),
        )
        return Response(OrderNoteSerializer(note).data, status=http_status.HTTP_201_CREATED)

    @extend_schema(responses={200: dict}, operation_id="admin_orders_queue")
    @action(detail=False, methods=["get"])
    def queue(self, request: Request) -> Response:
        """Orders waiting on the kitchen or counter, oldest first."""
        from .selectors import orders_needing_attention

        orders = orders_needing_attention(tenant_id=self.tenant_id)[:50]
        return Response(OrderListSerializer(orders, many=True).data)
