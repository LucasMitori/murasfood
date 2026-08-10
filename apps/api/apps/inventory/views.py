"""Inventory endpoints (merchant only)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import InventoryItem, StockMovement, StockReservation
from .serializers import (
    InventoryItemSerializer,
    StockAdjustmentSerializer,
    StockCountSerializer,
    StockMovementSerializer,
    StockReservationSerializer,
)
from .services import adjust_stock, low_stock_items, set_stock


class InventoryItemViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Stock levels. Quantities change only through the adjustment endpoints."""

    serializer_class = InventoryItemSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["inventory.view"],
        "retrieve": ["inventory.view"],
        "default": ["inventory.manage"],
    }
    queryset = InventoryItem.objects.select_related("product", "product__sale_unit").all()
    filterset_fields = ["track_stock", "product"]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self) -> Any:
        queryset = super().get_queryset()
        if self.request.query_params.get("low_stock") == "true":
            from django.db.models import F

            queryset = queryset.filter(
                track_stock=True, quantity__lte=F("reorder_threshold") + F("reserved_quantity")
            )
        return queryset.order_by("product__name")


class StockAdjustView(TenantScopedMixin, APIView):
    """Apply a signed stock change. Always writes a movement row."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.adjust"]

    @extend_schema(
        request=StockAdjustmentSerializer,
        responses={200: InventoryItemSerializer},
        operation_id="inventory_adjust",
    )
    def post(self, request: Request) -> Response:
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = Product.objects.filter(tenant_id=self.tenant_id, pk=data["product"]).first()
        if product is None:
            raise NotFoundError()

        item = adjust_stock(
            product=product,
            quantity_delta=data["quantity_delta"],
            movement_type=data["movement_type"],
            actor=request.user,
            note=data["note"],
        )
        return Response(InventoryItemSerializer(item).data)


class StockCountView(TenantScopedMixin, APIView):
    """Set an absolute quantity after a physical count."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.adjust"]

    @extend_schema(
        request=StockCountSerializer,
        responses={200: InventoryItemSerializer},
        operation_id="inventory_count",
    )
    def post(self, request: Request) -> Response:
        serializer = StockCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = Product.objects.filter(tenant_id=self.tenant_id, pk=data["product"]).first()
        if product is None:
            raise NotFoundError()

        item = set_stock(
            product=product, quantity=data["quantity"], actor=request.user, note=data["note"]
        )
        return Response(InventoryItemSerializer(item).data)


class StockMovementViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]
    queryset = StockMovement.objects.select_related("product", "actor").all()
    filterset_fields = ["product", "movement_type", "reference_type", "reference_id"]


class StockReservationViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockReservationSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]
    queryset = StockReservation.objects.select_related("product").all()
    filterset_fields = ["status", "order", "product"]


class LowStockView(TenantScopedMixin, APIView):
    """Items at or below their reorder threshold — the restocking worklist."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]

    @extend_schema(responses=InventoryItemSerializer(many=True), operation_id="inventory_low_stock")
    def get(self, request: Request) -> Response:
        items = low_stock_items(self.tenant_id, limit=100)
        return Response(InventoryItemSerializer(items, many=True).data)
