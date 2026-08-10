"""Pricing endpoints (merchant only — customers never see cost or margin)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import PriceHistory, ProductPrice
from .selectors import margin_metrics
from .serializers import (
    MarginAnalysisSerializer,
    PriceHistorySerializer,
    PriceWriteSerializer,
    ProductPriceSerializer,
)
from .services import bulk_adjust_prices, set_price


class ProductPriceViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Browse price rows. Writing goes through :class:`SetPriceView`."""

    serializer_class = ProductPriceSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.view"]
    queryset = ProductPrice.objects.select_related("product").all()
    filterset_fields = ["product", "is_active"]


class SetPriceView(TenantScopedMixin, APIView):
    """Set or update a product's price. Always writes history."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.update"]

    @extend_schema(
        request=PriceWriteSerializer,
        responses={200: ProductPriceSerializer},
        operation_id="pricing_set_price",
    )
    def post(self, request: Request) -> Response:
        serializer = PriceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = Product.objects.filter(tenant_id=self.tenant_id, pk=data.pop("product")).first()
        if product is None:
            raise NotFoundError()

        price = set_price(tenant=self.tenant, product=product, actor=request.user, **data)
        return Response(ProductPriceSerializer(price).data, status=status.HTTP_200_OK)


class BulkPriceAdjustView(TenantScopedMixin, APIView):
    """Shift many prices at once, e.g. a 5% increase across a category."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.update"]

    @extend_schema(request=None, responses={200: dict}, operation_id="pricing_bulk_adjust")
    def post(self, request: Request) -> Response:
        percentage = Decimal(str(request.data.get("percentage", "0")))
        product_ids = request.data.get("product_ids") or []
        category_id = request.data.get("category")

        products = Product.objects.filter(tenant_id=self.tenant_id)
        if product_ids:
            products = products.filter(pk__in=product_ids)
        elif category_id:
            products = products.filter(category_id=category_id)
        else:
            return Response(
                {"detail": "Provide product_ids or a category."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        changed = bulk_adjust_prices(
            tenant=self.tenant,
            products=list(products),
            percentage=percentage,
            actor=request.user,
            note=request.data.get("note", ""),
        )
        return Response({"updated": changed, "percentage": str(percentage)})


class PriceHistoryViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PriceHistorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.view"]
    queryset = PriceHistory.objects.select_related("changed_by", "product").all()
    filterset_fields = ["product", "field", "reason"]


class MarginAnalysisView(TenantScopedMixin, APIView):
    """Cost, price, margin and markup per product (spec §14)."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.view"]

    @extend_schema(
        responses=MarginAnalysisSerializer(many=True), operation_id="pricing_margin_analysis"
    )
    def get(self, request: Request) -> Response:
        from apps.orders.selectors import product_sales_totals
        from apps.pricing.selectors import annotate_effective_price

        products = annotate_effective_price(
            Product.objects.filter(tenant_id=self.tenant_id, is_active=True).select_related(
                "category"
            )
        ).order_by("name")[:500]

        sales = product_sales_totals(tenant_id=self.tenant_id)

        rows: list[dict[str, Any]] = []
        for product in products:
            price = product.effective_price
            if price is None:
                continue
            metrics = margin_metrics(price, product.cost_price)
            sold = sales.get(product.pk, {"units": 0, "revenue": Decimal("0.00")})
            rows.append(
                {
                    "product_id": product.pk,
                    "product_name": product.name,
                    "sku": product.sku,
                    "cost_price": str(product.cost_price)
                    if product.cost_price is not None
                    else None,
                    "sale_price": str(price),
                    "gross_margin": str(metrics["gross_margin"])
                    if metrics["gross_margin"] is not None
                    else None,
                    "gross_margin_percentage": str(metrics["gross_margin_percentage"])
                    if metrics["gross_margin_percentage"] is not None
                    else None,
                    "markup_percentage": str(metrics["markup_percentage"])
                    if metrics["markup_percentage"] is not None
                    else None,
                    "units_sold": int(sold["units"]),
                    "revenue": str(sold["revenue"]),
                }
            )
        return Response(MarginAnalysisSerializer(rows, many=True).data)


class ProductPriceHistoryView(TenantScopedMixin, APIView):
    """History for a single product, for the price chart on the product page."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["pricing.view"]

    @extend_schema(
        responses=PriceHistorySerializer(many=True), operation_id="pricing_product_history"
    )
    def get(self, request: Request, product_id: str) -> Response:
        history = (
            PriceHistory.objects.filter(tenant_id=self.tenant_id, product_id=product_id)
            .select_related("changed_by")
            .order_by("-created_at")[:100]
        )
        return Response(PriceHistorySerializer(history, many=True).data)


class ProductPriceActionsMixin:
    """Shared helper for viewsets that expose a "current price" action."""

    @action(detail=True, methods=["get"])
    def current_price(self, request: Request, pk: str | None = None) -> Response:
        from .selectors import resolve_price

        product = self.get_object()  # type: ignore[attr-defined]
        resolved = resolve_price(product)
        if resolved is None:
            raise NotFoundError()
        return Response(
            {
                "unit_price": str(resolved.unit_price),
                "base_price": str(resolved.base_price),
                "is_discounted": resolved.is_discounted,
            }
        )
