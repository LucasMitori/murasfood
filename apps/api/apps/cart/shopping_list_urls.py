"""Shopping list routes, mounted at ``/shopping-lists/``."""

from django.urls import path

from .shopping_list_views import (
    SaveCartAsListView,
    ShoppingListAddToCartView,
    ShoppingListDetailView,
    ShoppingListItemDetailView,
    ShoppingListItemsView,
    ShoppingListsView,
)

app_name = "shopping_lists"

urlpatterns = [
    path("", ShoppingListsView.as_view(), name="list"),
    # Before `<uuid:list_id>/` so the literal segment is not read as an id.
    path("from-cart/", SaveCartAsListView.as_view(), name="from-cart"),
    path("<uuid:list_id>/", ShoppingListDetailView.as_view(), name="detail"),
    path("<uuid:list_id>/items/", ShoppingListItemsView.as_view(), name="items"),
    path(
        "<uuid:list_id>/items/<uuid:item_id>/",
        ShoppingListItemDetailView.as_view(),
        name="item-detail",
    ),
    path(
        "<uuid:list_id>/add-to-cart/",
        ShoppingListAddToCartView.as_view(),
        name="add-to-cart",
    ),
]
