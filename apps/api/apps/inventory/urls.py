from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ExpiryReportView,
    InventoryItemViewSet,
    LowStockView,
    StockAdjustView,
    StockBatchViewSet,
    StockCountView,
    StockHealthView,
    StockMovementViewSet,
    StockReservationViewSet,
)

app_name = "inventory"

router = DefaultRouter()
router.register("inventory", InventoryItemViewSet, basename="inventory")
router.register("stock-batches", StockBatchViewSet, basename="stock-batch")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("stock-reservations", StockReservationViewSet, basename="stock-reservation")

urlpatterns = [
    path("inventory/adjust/", StockAdjustView.as_view(), name="adjust"),
    path("inventory/count/", StockCountView.as_view(), name="count"),
    path("inventory/low-stock/", LowStockView.as_view(), name="low-stock"),
    path("inventory/expiry/", ExpiryReportView.as_view(), name="expiry-report"),
    path("inventory/health/", StockHealthView.as_view(), name="stock-health"),
    path("", include(router.urls)),
]
