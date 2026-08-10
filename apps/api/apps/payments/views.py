"""Payment endpoints, including the provider webhook."""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin
from apps.orders.models import Order

from .models import Payment, PaymentEvent, PaymentRefund
from .serializers import (
    CreatePaymentSerializer,
    PaymentAdminSerializer,
    PaymentEventSerializer,
    PaymentPublicSerializer,
    PaymentRefundSerializer,
    RefundRequestSerializer,
)
from .services import create_payment_for_order, process_webhook, reconcile_payment, refund_payment


@method_decorator(csrf_exempt, name="dispatch")
class PaymentWebhookView(APIView):
    """Receives provider callbacks.

    Unauthenticated by necessity — the provider has no session — but *not*
    untrusted: the signature is verified before the body is interpreted, and the
    event id makes replays no-ops (invariants #4 and #5).

    Deliberately returns 200 for duplicates and unknown references so a provider
    stops retrying events we have already handled or will never understand.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []

    @extend_schema(
        request=None,
        responses={200: dict},
        operation_id="payments_webhook",
        description="Provider payment callback. Requires a valid signature header.",
    )
    def post(self, request: Request, provider: str | None = None) -> Response:
        headers = dict(request.headers.items())
        result = process_webhook(raw_body=request.body, headers=headers, provider_name=provider)
        return Response(result, status=http_status.HTTP_200_OK)


class PaymentDetailView(TenantScopedMixin, APIView):
    """The customer's view of their payment, for the PIX screen to poll."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PaymentPublicSerializer, operation_id="payments_retrieve")
    def get(self, request: Request, pk: str) -> Response:
        payment = (
            Payment.objects.filter(pk=pk, tenant_id=self.tenant_id).select_related("order").first()
        )
        if payment is None or payment.order.customer_id != request.user.pk:
            raise NotFoundError()
        return Response(PaymentPublicSerializer(payment).data)


class OrderPaymentView(TenantScopedMixin, APIView):
    """Open (or re-open) the payment for one of the caller's orders."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CreatePaymentSerializer,
        responses={201: PaymentPublicSerializer},
        operation_id="payments_create",
    )
    def post(self, request: Request) -> Response:
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = Order.objects.filter(
            pk=serializer.validated_data["order"],
            tenant_id=self.tenant_id,
            customer=request.user,
        ).first()
        if order is None:
            raise NotFoundError()

        payment = create_payment_for_order(
            order=order, method=serializer.validated_data.get("method", "PIX")
        )
        return Response(PaymentPublicSerializer(payment).data, status=http_status.HTTP_201_CREATED)


class PaymentAdminViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Merchant payment list and refund action."""

    serializer_class = PaymentAdminSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"refund": ["payments.refund"], "default": ["payments.view"]}
    filterset_fields = ["status", "method", "provider", "order"]

    def get_queryset(self) -> Any:
        return (
            Payment.objects.for_tenant(self.tenant_id)
            .select_related("order")
            .order_by("-created_at")
        )

    @extend_schema(
        request=RefundRequestSerializer,
        responses={201: PaymentRefundSerializer},
        operation_id="admin_payments_refund",
    )
    @action(detail=True, methods=["post"])
    def refund(self, request: Request, pk: str | None = None) -> Response:
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refund = refund_payment(
            payment=self.get_object(),
            amount=serializer.validated_data["amount"],
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(PaymentRefundSerializer(refund).data, status=http_status.HTTP_201_CREATED)

    @extend_schema(
        request=None, responses=PaymentAdminSerializer, operation_id="admin_payments_reconcile"
    )
    @action(detail=True, methods=["post"])
    def reconcile(self, request: Request, pk: str | None = None) -> Response:
        """Re-query the provider when a webhook appears to have been lost."""
        payment = reconcile_payment(self.get_object())
        return Response(PaymentAdminSerializer(payment).data)


class PaymentEventViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """The webhook ledger — the first place to look when a payment misbehaves."""

    serializer_class = PaymentEventSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["payments.view"]
    filterset_fields = ["processing_status", "event_type", "payment"]

    def get_queryset(self) -> Any:
        return PaymentEvent.objects.for_tenant(self.tenant_id).order_by("-created_at")


class PaymentRefundViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentRefundSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["payments.view"]
    filterset_fields = ["status", "payment"]

    def get_queryset(self) -> Any:
        return PaymentRefund.objects.for_tenant(self.tenant_id).order_by("-created_at")


class SandboxWebhookSimulatorView(TenantScopedMixin, APIView):
    """Development helper: fire a correctly signed sandbox webhook.

    Refuses to run unless the sandbox provider is configured, so it can never
    confirm a real payment. It signs the body with the same secret a provider
    would use, exercising the production verification path rather than bypassing
    it.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["payments.view"]

    @extend_schema(
        request=None, responses={200: dict}, operation_id="payments_sandbox_simulate", exclude=True
    )
    def post(self, request: Request, pk: str) -> Response:
        if settings.PAYMENT_PROVIDER != "sandbox":
            return Response(
                {"detail": "Only available with the sandbox provider."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        payment = Payment.objects.filter(pk=pk, tenant_id=self.tenant_id).first()
        if payment is None:
            raise NotFoundError()

        from .providers.sandbox import SIGNATURE_HEADER, SandboxPixProvider

        body = json.dumps(
            {
                "id": f"sim_{payment.pk.hex[:12]}",
                "type": "payment.paid",
                "payment_id": payment.external_id,
                "status": request.data.get("status", "PAID"),
                "amount": str(payment.amount),
                "fee": request.data.get("fee", "0.00"),
            }
        ).encode("utf-8")

        result = process_webhook(
            raw_body=body,
            headers={SIGNATURE_HEADER: SandboxPixProvider.sign(body)},
            provider_name="sandbox",
        )
        return Response(result)
