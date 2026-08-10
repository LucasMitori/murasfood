from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerReportView,
    DashboardView,
    InventoryReportView,
    ReportExportView,
    ReportJobViewSet,
    SalesReportView,
)

app_name = "reports"

router = DefaultRouter()
router.register("report-jobs", ReportJobViewSet, basename="report-job")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reports/sales/", SalesReportView.as_view(), name="sales"),
    path("reports/inventory/", InventoryReportView.as_view(), name="inventory"),
    path("reports/customers/", CustomerReportView.as_view(), name="customers"),
    path("reports/export/", ReportExportView.as_view(), name="export"),
    path("", include(router.urls)),
]
