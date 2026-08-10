"""Delivery endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import DeliveryZone
from .selectors import available_methods, get_settings, public_delivery_config
from .serializers import (
    DeliveryQuoteRequestSerializer,
    DeliverySettingsSerializer,
    DeliveryZoneSerializer,
)


class DeliveryOptionsView(TenantScopedMixin, APIView):
    """Priced delivery options for a postal code and cart subtotal."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=DeliveryQuoteRequestSerializer,
        responses={200: dict},
        operation_id="delivery_options",
    )
    def post(self, request: Request) -> Response:
        serializer = DeliveryQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subtotal = serializer.validated_data.get("subtotal")
        if subtotal is None:
            # Fall back to the caller's live cart so the client does not have to
            # send an amount the server would recompute anyway.
            from apps.cart.selectors import current_cart_for

            cart = current_cart_for(request=request, tenant=self.tenant, create=False)
            subtotal = cart.subtotal if cart else Decimal("0.00")

        return Response(
            {
                "config": public_delivery_config(self.tenant),
                "options": available_methods(
                    self.tenant,
                    subtotal=subtotal,
                    postal_code=serializer.validated_data.get("postal_code", ""),
                ),
            }
        )


class DeliveryConfigView(TenantScopedMixin, APIView):
    """Public delivery configuration."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict}, operation_id="delivery_config")
    def get(self, request: Request) -> Response:
        return Response(public_delivery_config(self.tenant))


class DeliverySettingsView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    @extend_schema(responses=DeliverySettingsSerializer, operation_id="delivery_settings_retrieve")
    def get(self, request: Request) -> Response:
        return Response(DeliverySettingsSerializer(get_settings(self.tenant)).data)

    @extend_schema(
        request=DeliverySettingsSerializer,
        responses=DeliverySettingsSerializer,
        operation_id="delivery_settings_update",
    )
    def patch(self, request: Request) -> Response:
        serializer = DeliverySettingsSerializer(
            get_settings(self.tenant), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DeliveryZoneViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = DeliveryZoneSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["orders.view"], "default": ["tenant.settings"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return DeliveryZone.objects.for_tenant(self.tenant_id).order_by("postal_code_start")
