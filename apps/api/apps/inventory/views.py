"""Inventory endpoints (merchant only)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.common import spreadsheets
from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import InventoryItem, StockBatch, StockMovement, StockReservation
from .serializers import (
    InventoryItemSerializer,
    RestockDemandSerializer,
    StockAdjustmentSerializer,
    StockBatchSerializer,
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
    search_fields = ["product__name", "product__sku", "location"]

    @extend_schema(
        parameters=[OpenApiParameter("fmt", str, description="csv or xlsx")],
        responses={200: OpenApiTypes.BINARY},
        operation_id="admin_inventory_export",
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request: Request) -> Any:
        """The stock list, for counting against on paper.

        Exports what the screen is showing — the same filters and search — so a
        merchant who narrowed to "out of stock" gets that list rather than all
        four hundred items.
        """
        from apps.common.exports import INVENTORY_COLUMNS, inventory_rows

        return spreadsheets.download(
            columns=INVENTORY_COLUMNS,
            rows=inventory_rows(self.filter_queryset(self.get_queryset())),
            stem="estoque",
            fmt=request.query_params.get("fmt", spreadsheets.XLSX),
        )

    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self) -> Any:
        queryset = super().get_queryset()
        params = self.request.query_params

        if params.get("low_stock") == "true":
            queryset = queryset.filter(_low_stock_q())

        # The four states a shopkeeper acts on. Expressed here rather than in
        # the client so the counts on a summary and the rows in a list are
        # derived from the same rule and cannot drift apart.
        state = params.get("stock_state")
        if state:
            queryset = _filter_by_state(queryset, state)

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


class StockBatchViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Lots of stock and the dates they stop being sellable.

    Filters are query parameters rather than separate endpoints because the
    three questions an operator asks — *what has expired*, *what is about to*,
    and *what is in this product* — are the same list under different windows,
    and one list keeps sorting and pagination consistent between them.
    """

    serializer_class = StockBatchSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["inventory.view"],
        "retrieve": ["inventory.view"],
        "default": ["inventory.manage"],
    }
    queryset = StockBatch.objects.select_related("product", "product__sale_unit").all()
    filterset_fields = ["product"]
    search_fields = ["product__name", "product__sku", "code", "supplier"]

    def get_queryset(self) -> Any:
        queryset = super().get_queryset()
        params = self.request.query_params

        if params.get("remaining") == "true":
            queryset = queryset.remaining()

        if params.get("expired") == "true":
            queryset = queryset.expired()

        window = params.get("expiring_days")
        if window:
            try:
                days = int(window)
            except ValueError:
                # A malformed window is a caller bug, not a reason to answer
                # with every batch ever received.
                raise ValidationError(
                    {"expiring_days": _("Must be a whole number of days.")}
                ) from None
            queryset = queryset.expiring_within(max(days, 0))

        return queryset


class ExpiryReportView(TenantScopedMixin, APIView):
    """What is going off, summarised for a dashboard.

    Answers in one request what a shop checks every morning: how much has
    already expired, how much turns this week, and what that is worth if it is
    thrown away.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]

    @extend_schema(responses={200: dict}, operation_id="inventory_expiry_report")
    def get(self, request: Request) -> Response:
        try:
            days = int(request.query_params.get("days", 7))
        except ValueError:
            raise ValidationError({"days": _("Must be a whole number of days.")}) from None

        days = max(days, 0)
        batches = StockBatch.objects.for_tenant(request.tenant)

        expired = batches.expired().select_related("product")
        soon = batches.expiring_within(days).select_related("product")

        def value_of(queryset: Any) -> Decimal:
            """Only batches with a known cost contribute; the rest are unknown,
            not zero, and quietly counting them as zero would understate it."""
            total = Decimal("0.00")
            for batch in queryset:
                worth = batch.write_off_value
                if worth is not None:
                    total += worth
            return total

        return Response(
            {
                "days": days,
                "expired_count": expired.count(),
                "expired_value": str(value_of(expired)),
                "expiring_count": soon.count(),
                "expiring_value": str(value_of(soon)),
                "expired": StockBatchSerializer(expired[:20], many=True).data,
                "expiring": StockBatchSerializer(soon[:20], many=True).data,
            }
        )


def _low_stock_q() -> Q:
    """Tracked, still has some, and at or under the point it should be reordered."""
    return Q(track_stock=True, quantity__lte=F("reorder_threshold") + F("reserved_quantity"))


def _out_of_stock_q() -> Q:
    """Nothing sellable left. Available is derived, so the comparison is too."""
    return Q(track_stock=True, quantity__lte=F("reserved_quantity"))


def _filter_by_state(queryset: Any, state: str) -> Any:
    if state == "out":
        return queryset.filter(_out_of_stock_q())
    if state == "low":
        # Low means running down, not gone: what is already out belongs in the
        # other band, and counting it twice would overstate both.
        return queryset.filter(_low_stock_q()).exclude(_out_of_stock_q())
    if state == "healthy":
        return queryset.filter(track_stock=True).exclude(_low_stock_q())
    if state == "untracked":
        return queryset.filter(track_stock=False)

    raise ValidationError({"stock_state": _("Unknown stock state.")})


class StockHealthView(TenantScopedMixin, APIView):
    """How many products sit in each state.

    One request rather than four so the numbers describe a single moment. Four
    separate counts taken as stock moves can disagree with each other and with
    the list beside them, which makes the summary look broken.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]

    @extend_schema(responses={200: dict}, operation_id="inventory_stock_health")
    def get(self, request: Request) -> Response:
        items = InventoryItem.objects.for_tenant(request.tenant)

        tracked = items.filter(track_stock=True)
        out = tracked.filter(_out_of_stock_q()).count()
        low = tracked.filter(_low_stock_q()).exclude(_out_of_stock_q()).count()

        return Response(
            {
                "out": out,
                "low": low,
                "healthy": tracked.count() - out - low,
                "untracked": items.filter(track_stock=False).count(),
            }
        )


class RestockDemandView(TenantScopedMixin, APIView):
    """What shoppers asked to be told about, ranked by how many asked.

    The only view in the system onto demand that produced no order. A product
    with forty people waiting is a buying decision; the sales report will never
    show it, because nothing was sold.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["inventory.view"]

    @extend_schema(
        parameters=[OpenApiParameter("limit", int, description="Rows to return, max 200.")],
        responses=RestockDemandSerializer(many=True),
        operation_id="inventory_restock_demand",
    )
    def get(self, request: Request) -> Response:
        from .services import restock_demand

        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        return Response(restock_demand(self.tenant_id, limit=max(1, limit)))
