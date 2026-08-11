"""Shopping list endpoints.

A shopping list belongs to one customer. Every queryset here is filtered by
both tenant and ``customer=request.user`` — not only tenant — so one shopper
cannot read or edit another's list even inside the same merchant.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.common.exceptions import NotFoundError
from apps.common.views import TenantScopedMixin

from .models import ShoppingList, ShoppingListItem
from .selectors import current_cart_for
from .serializers import (
    SaveCartAsListSerializer,
    ShoppingListItemWriteSerializer,
    ShoppingListSerializer,
    ShoppingListSummarySerializer,
    ShoppingListWriteSerializer,
)
from .services import (
    add_list_to_cart,
    create_list_from_cart,
    create_shopping_list,
    remove_list_item,
    rename_shopping_list,
    set_list_item,
)


class ShoppingListBaseView(TenantScopedMixin, APIView):
    permission_classes = [IsAuthenticated]

    def owned_lists(self) -> Any:
        """Every read and write starts here, so ownership cannot be forgotten."""
        return ShoppingList.objects.filter(tenant_id=self.tenant_id, customer=self.request.user)

    def detailed(self) -> Any:
        return self.owned_lists().prefetch_related(
            Prefetch(
                "items",
                queryset=ShoppingListItem.objects.select_related(
                    "product", "product__sale_unit", "product__category", "product__inventory"
                ).prefetch_related("product__images__asset"),
            )
        )

    def get_list(self, list_id: str) -> ShoppingList:
        shopping_list = self.detailed().filter(pk=list_id).first()
        if shopping_list is None:
            # 404 rather than 403: another customer's list should not be
            # confirmed to exist.
            raise NotFoundError(details={"resource": "shopping_list"})
        return shopping_list

    def list_response(
        self, shopping_list: ShoppingList, *, status_code: int = status.HTTP_200_OK
    ) -> Response:
        fresh = self.detailed().get(pk=shopping_list.pk)
        return Response(
            ShoppingListSerializer(fresh, context={"request": self.request}).data,
            status=status_code,
        )


class ShoppingListsView(ShoppingListBaseView):
    @extend_schema(
        responses=ShoppingListSummarySerializer(many=True), operation_id="shopping_lists_list"
    )
    def get(self, request: Request) -> Response:
        lists = self.owned_lists().annotate(item_count=Count("items")).order_by("name")
        return Response(ShoppingListSummarySerializer(lists, many=True).data)

    @extend_schema(
        request=ShoppingListWriteSerializer,
        responses={201: ShoppingListSerializer},
        operation_id="shopping_lists_create",
    )
    def post(self, request: Request) -> Response:
        serializer = ShoppingListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shopping_list = create_shopping_list(
            tenant=self.tenant,
            customer=request.user,
            name=serializer.validated_data["name"],
            note=serializer.validated_data.get("note", ""),
        )
        return self.list_response(shopping_list, status_code=status.HTTP_201_CREATED)


class ShoppingListDetailView(ShoppingListBaseView):
    @extend_schema(responses=ShoppingListSerializer, operation_id="shopping_lists_retrieve")
    def get(self, request: Request, list_id: str) -> Response:
        return Response(
            ShoppingListSerializer(self.get_list(list_id), context={"request": request}).data
        )

    @extend_schema(
        request=ShoppingListWriteSerializer,
        responses=ShoppingListSerializer,
        operation_id="shopping_lists_update",
    )
    def patch(self, request: Request, list_id: str) -> Response:
        shopping_list = self.get_list(list_id)
        serializer = ShoppingListWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        if "name" in serializer.validated_data:
            rename_shopping_list(
                shopping_list=shopping_list, name=serializer.validated_data["name"]
            )
        if "note" in serializer.validated_data:
            shopping_list.note = serializer.validated_data["note"][:255]
            shopping_list.save(update_fields=["note", "updated_at"])

        return self.list_response(shopping_list)

    @extend_schema(responses={204: None}, operation_id="shopping_lists_delete")
    def delete(self, request: Request, list_id: str) -> Response:
        self.get_list(list_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ShoppingListItemsView(ShoppingListBaseView):
    @extend_schema(
        request=ShoppingListItemWriteSerializer,
        responses={201: ShoppingListSerializer},
        operation_id="shopping_lists_add_item",
    )
    def post(self, request: Request, list_id: str) -> Response:
        shopping_list = self.get_list(list_id)
        serializer = ShoppingListItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = (
            Product.objects.filter(tenant_id=self.tenant_id, pk=data["product"])
            .select_related("sale_unit")
            .first()
        )
        if product is None:
            raise NotFoundError()

        set_list_item(
            shopping_list=shopping_list,
            product=product,
            quantity=data.get("quantity") or 1,
            note=data.get("note", ""),
        )
        return self.list_response(shopping_list, status_code=status.HTTP_201_CREATED)


class ShoppingListItemDetailView(ShoppingListBaseView):
    def get_item(self, shopping_list: ShoppingList, item_id: str) -> ShoppingListItem:
        item = ShoppingListItem.objects.filter(shopping_list=shopping_list, pk=item_id).first()
        if item is None:
            raise NotFoundError(details={"resource": "shopping_list_item"})
        return item

    @extend_schema(
        request=ShoppingListItemWriteSerializer,
        responses=ShoppingListSerializer,
        operation_id="shopping_lists_update_item",
    )
    def patch(self, request: Request, list_id: str, item_id: str) -> Response:
        shopping_list = self.get_list(list_id)
        item = self.get_item(shopping_list, item_id)

        serializer = ShoppingListItemWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        set_list_item(
            shopping_list=shopping_list,
            product=item.product,
            quantity=serializer.validated_data.get("quantity") or item.quantity,
            note=serializer.validated_data.get("note", item.note),
        )
        return self.list_response(shopping_list)

    @extend_schema(responses=ShoppingListSerializer, operation_id="shopping_lists_remove_item")
    def delete(self, request: Request, list_id: str, item_id: str) -> Response:
        shopping_list = self.get_list(list_id)
        remove_list_item(shopping_list=shopping_list, item=self.get_item(shopping_list, item_id))
        return self.list_response(shopping_list)


class ShoppingListAddToCartView(ShoppingListBaseView):
    @extend_schema(request=None, responses={200: dict}, operation_id="shopping_lists_add_to_cart")
    def post(self, request: Request, list_id: str) -> Response:
        """Copy the list into the cart.

        Returns which products went in and which did not, because a partial
        result is the normal case: a list kept for months will eventually name
        something that is out of stock or no longer sold.
        """
        shopping_list = self.get_list(list_id)
        cart = current_cart_for(request=request, tenant=self.tenant, create=True)
        if cart is None:  # pragma: no cover - create=True always returns one
            raise NotFoundError(details={"resource": "cart"})

        return Response(add_list_to_cart(shopping_list=shopping_list, cart=cart))


class SaveCartAsListView(ShoppingListBaseView):
    @extend_schema(
        request=SaveCartAsListSerializer,
        responses={201: ShoppingListSerializer},
        operation_id="shopping_lists_from_cart",
    )
    def post(self, request: Request) -> Response:
        serializer = SaveCartAsListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = current_cart_for(request=request, tenant=self.tenant, create=False)
        if cart is None or cart.is_empty:
            raise NotFoundError(details={"resource": "cart"})

        shopping_list = create_list_from_cart(
            cart=cart,
            customer=request.user,
            name=serializer.validated_data["name"],
            note=serializer.validated_data.get("note", ""),
        )
        return self.list_response(shopping_list, status_code=status.HTTP_201_CREATED)
