"""Promotion endpoints."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import Coupon, CouponRedemption, Promotion
from .serializers import (
    CouponRedemptionSerializer,
    CouponSerializer,
    CouponValidateSerializer,
    PromotionPublicSerializer,
    PromotionSerializer,
)
from .services import active_promotions, validate_coupon


class PublicPromotionListView(TenantScopedMixin, APIView):
    """Promotions the storefront can advertise (no coupon-only rules)."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses=PromotionPublicSerializer(many=True), operation_id="promotions_public_list"
    )
    def get(self, request: Request) -> Response:
        promotions = active_promotions(self.tenant)
        return Response(PromotionPublicSerializer(promotions, many=True).data)


class CouponValidateView(TenantScopedMixin, APIView):
    """Check a coupon against the current cart before checkout.

    Returns the discount this coupon *would* produce. The number is recomputed
    at checkout regardless — this is a preview, not a promise the client can
    hold the server to.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CouponValidateSerializer,
        responses={200: dict},
        operation_id="promotions_validate_coupon",
    )
    def post(self, request: Request) -> Response:
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.cart.selectors import current_cart_for
        from apps.cart.services import cart_discount_preview

        cart = current_cart_for(request=request, tenant=self.tenant, create=False)
        subtotal = cart.subtotal if cart else 0

        coupon = validate_coupon(
            tenant=self.tenant,
            code=serializer.validated_data["code"],
            customer=request.user,
            subtotal=subtotal,
        )
        preview = cart_discount_preview(cart, coupon_code=coupon.code) if cart else None

        return Response(
            {
                "code": coupon.code,
                "valid": True,
                "promotion": PromotionPublicSerializer(coupon.promotion).data,
                "discount": str(preview.total_discount) if preview else "0.00",
                "free_delivery": bool(preview and preview.free_delivery),
            }
        )


class PromotionViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["promotions.view"], "default": ["promotions.manage"]}
    filterset_fields = ["is_active", "discount_type", "scope", "requires_coupon"]

    def get_queryset(self) -> Any:
        return (
            Promotion.objects.for_tenant(self.tenant_id)
            .prefetch_related("products", "categories")
            .order_by("-priority", "-created_at")
        )


class CouponViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["promotions.view"], "default": ["promotions.manage"]}
    filterset_fields = ["is_active", "promotion"]

    def get_queryset(self) -> Any:
        return (
            Coupon.objects.for_tenant(self.tenant_id)
            .select_related("promotion")
            .order_by("-created_at")
        )


class CouponRedemptionViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CouponRedemptionSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["promotions.view"]
    filterset_fields = ["coupon", "customer", "order"]

    def get_queryset(self) -> Any:
        return (
            CouponRedemption.objects.for_tenant(self.tenant_id)
            .select_related("coupon")
            .order_by("-created_at")
        )
