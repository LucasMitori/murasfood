from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BulkPriceAdjustView,
    MarginAnalysisView,
    PriceHistoryViewSet,
    ProductPriceHistoryView,
    ProductPriceViewSet,
    SetPriceView,
)

app_name = "pricing"

router = DefaultRouter()
router.register("prices", ProductPriceViewSet, basename="price")
router.register("price-history", PriceHistoryViewSet, basename="price-history")

urlpatterns = [
    path("prices/set/", SetPriceView.as_view(), name="set-price"),
    path("prices/bulk-adjust/", BulkPriceAdjustView.as_view(), name="bulk-adjust"),
    path("prices/margins/", MarginAnalysisView.as_view(), name="margins"),
    path(
        "prices/history/<uuid:product_id>/",
        ProductPriceHistoryView.as_view(),
        name="product-history",
    ),
    path("", include(router.urls)),
]
