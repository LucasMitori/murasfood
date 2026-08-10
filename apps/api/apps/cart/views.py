"""Cart endpoints.

Anonymous shoppers get a cart token in the ``X-Cart-Token`` response header;
sending it back on subsequent requests keeps their cart. Once they sign in, the
token is ignored in favour of their account cart, and
``POST /cart/merge/`` folds the anonymous one in.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.common.exceptions import NotFoundError
from apps.common.views import TenantScopedMixin

from .models import Cart, CartItem, CartStatus
from .selectors import cart_queryset, cart_totals, current_cart_for
from .serializers import (
    AddItemSerializer,
    ApplyCouponSerializer,
    CartSerializer,
    UpdateItemSerializer,
)
from .services import (
    add_item,
    apply_coupon,
    clear_cart,
    merge_carts,
    remove_coupon,
    remove_item,
    set_item_quantity,
)

CART_TOKEN_RESPONSE_HEADER = "X-Cart-Token"


class CartBaseView(TenantScopedMixin, APIView):
    """Shared cart resolution and response shaping."""

    permission_classes = [AllowAny]

    def get_cart(self, *, create: bool = True) -> Cart:
        cart = current_cart_for(request=self.request, tenant=self.tenant, create=create)
        if cart is None:
            raise NotFoundError(details={"resource": "cart"})
        return cart

    def cart_response(self, cart: Cart, *, status_code: int = status.HTTP_200_OK) -> Response:
        fresh = cart_queryset().get(pk=cart.pk)
        response = Response(
            CartSerializer(fresh, context={"request": self.request}).data, status=status_code
        )
        # Anonymous clients need the token to find this cart again.
        if fresh.customer_id is None:
            response[CART_TOKEN_RESPONSE_HEADER] = fresh.token
        return response


class CartView(CartBaseView):
    """Read or empty the current cart."""

    @extend_schema(
        parameters=[
            OpenApiParameter("delivery_method", str, description="PICKUP or DELIVERY"),
            OpenApiParameter("postal_code", str),
        ],
        responses=CartSerializer,
        operation_id="cart_retrieve",
    )
    def get(self, request: Request) -> Response:
        return self.cart_response(self.get_cart())

    @extend_schema(responses=CartSerializer, operation_id="cart_clear")
    def delete(self, request: Request) -> Response:
        cart = self.get_cart(create=False)
        clear_cart(cart)
        return self.cart_response(cart)


class CartItemsView(CartBaseView):
    """Add a product to the cart."""

    @extend_schema(
        request=AddItemSerializer, responses={201: CartSerializer}, operation_id="cart_add_item"
    )
    def post(self, request: Request) -> Response:
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = (
            Product.objects.filter(tenant_id=self.tenant_id, pk=data["product"])
            .select_related("sale_unit", "inventory")
            .first()
        )
        if product is None:
            raise NotFoundError()

        cart = self.get_cart()
        add_item(
            cart=cart,
            product=product,
            quantity=data.get("quantity") or Decimal("1"),
            note=data.get("note", ""),
        )
        return self.cart_response(cart, status_code=status.HTTP_201_CREATED)


class CartItemDetailView(CartBaseView):
    """Change or remove one line."""

    def _get_item(self, cart: Cart, item_id: Any) -> CartItem:
        item = CartItem.objects.filter(cart=cart, pk=item_id).select_related("product").first()
        if item is None:
            raise NotFoundError()
        return item

    @extend_schema(
        request=UpdateItemSerializer, responses=CartSerializer, operation_id="cart_update_item"
    )
    def patch(self, request: Request, item_id: str) -> Response:
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self.get_cart(create=False)
        item = self._get_item(cart, item_id)
        set_item_quantity(cart=cart, item=item, quantity=serializer.validated_data["quantity"])
        return self.cart_response(cart)

    @extend_schema(responses=CartSerializer, operation_id="cart_remove_item")
    def delete(self, request: Request, item_id: str) -> Response:
        cart = self.get_cart(create=False)
        remove_item(cart=cart, item=self._get_item(cart, item_id))
        return self.cart_response(cart)


class CartCouponView(CartBaseView):
    """Apply or drop a coupon."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ApplyCouponSerializer, responses=CartSerializer, operation_id="cart_apply_coupon"
    )
    def post(self, request: Request) -> Response:
        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self.get_cart()
        apply_coupon(cart=cart, code=serializer.validated_data["code"])
        return self.cart_response(cart)

    @extend_schema(responses=CartSerializer, operation_id="cart_remove_coupon")
    def delete(self, request: Request) -> Response:
        cart = self.get_cart(create=False)
        remove_coupon(cart)
        return self.cart_response(cart)


class CartMergeView(CartBaseView):
    """Merge an anonymous cart into the signed-in customer's cart."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=CartSerializer, operation_id="cart_merge")
    def post(self, request: Request) -> Response:
        token = (request.data.get("cart_token") or "").strip()
        if not token:
            return self.cart_response(self.get_cart())

        anonymous = Cart.objects.filter(
            tenant_id=self.tenant_id,
            token=token,
            customer__isnull=True,
            status=CartStatus.ACTIVE,
        ).first()
        if anonymous is None:
            return self.cart_response(self.get_cart())

        merged = merge_carts(anonymous_cart=anonymous, customer=request.user)
        return self.cart_response(merged)


class CartSummaryView(CartBaseView):
    """Totals only — used by the header badge, which does not need line items."""

    @extend_schema(responses={200: dict}, operation_id="cart_summary")
    def get(self, request: Request) -> Response:
        cart = current_cart_for(request=request, tenant=self.tenant, create=False)
        return Response(
            cart_totals(
                cart,
                delivery_method=request.query_params.get("delivery_method"),
                postal_code=request.query_params.get("postal_code", ""),
            )
        )
