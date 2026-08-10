from django.urls import path

from .views import (
    CartCouponView,
    CartItemDetailView,
    CartItemsView,
    CartMergeView,
    CartSummaryView,
    CartView,
)

app_name = "cart"

urlpatterns = [
    path("", CartView.as_view(), name="detail"),
    path("summary/", CartSummaryView.as_view(), name="summary"),
    path("items/", CartItemsView.as_view(), name="items"),
    path("items/<uuid:item_id>/", CartItemDetailView.as_view(), name="item-detail"),
    path("coupon/", CartCouponView.as_view(), name="coupon"),
    path("merge/", CartMergeView.as_view(), name="merge"),
]
