"""Dashboard and report endpoints."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import ReportJob
from .periods import build_period, resolve_period
from .serializers import DashboardSerializer, ReportJobSerializer, ReportRequestSerializer
from .services import dashboard_summary, inventory_report, queue_report, sales_report

PERIOD_PARAMETERS = [
    OpenApiParameter(
        "period",
        str,
        description="today | yesterday | last_7 | last_30 | month | previous_month | year | custom",
    ),
    OpenApiParameter("start", str, description="ISO date, used with period=custom"),
    OpenApiParameter("end", str, description="ISO date, used with period=custom"),
]


class DashboardView(TenantScopedMixin, APIView):
    """Merchant dashboard.

    One request returns every metric and chart series, all aggregated in
    PostgreSQL. The browser renders; it does not compute.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.view"]

    @extend_schema(
        parameters=PERIOD_PARAMETERS,
        responses=DashboardSerializer,
        operation_id="admin_dashboard",
    )
    def get(self, request: Request) -> Response:
        period = resolve_period(request, tenant=self.tenant)
        return Response(dashboard_summary(tenant=self.tenant, period=period))


class SalesReportView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.view"]

    @extend_schema(
        parameters=PERIOD_PARAMETERS, responses={200: dict}, operation_id="reports_sales"
    )
    def get(self, request: Request) -> Response:
        period = resolve_period(request, tenant=self.tenant)
        return Response(sales_report(tenant=self.tenant, period=period))


class InventoryReportView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.view"]

    @extend_schema(responses={200: dict}, operation_id="reports_inventory")
    def get(self, request: Request) -> Response:
        return Response(inventory_report(tenant=self.tenant))


class CustomerReportView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.view"]

    @extend_schema(
        parameters=PERIOD_PARAMETERS, responses={200: dict}, operation_id="reports_customers"
    )
    def get(self, request: Request) -> Response:
        from apps.orders.selectors import customer_metrics

        period = resolve_period(request, tenant=self.tenant)
        return Response(
            {
                "period": {
                    "start": period.start_date.isoformat(),
                    "end": period.end_date.isoformat(),
                },
                **customer_metrics(tenant_id=self.tenant_id, start=period.start, end=period.end),
            }
        )


class ReportJobViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Queued exports. The client polls until ``is_ready``."""

    serializer_class = ReportJobSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.view"]
    filterset_fields = ["report_type", "status"]

    def get_queryset(self) -> Any:
        return (
            ReportJob.objects.for_tenant(self.tenant_id)
            .select_related("asset")
            .order_by("-created_at")
        )


class ReportExportView(TenantScopedMixin, APIView):
    """Request a PDF export.

    Returns 202 with a job id rather than the file: a year of sales can take
    long enough that holding the request open would time out (spec §28).
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["reports.export"]

    @extend_schema(
        request=ReportRequestSerializer,
        responses={202: ReportJobSerializer},
        operation_id="reports_export",
    )
    def post(self, request: Request) -> Response:
        serializer = ReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("start") and data.get("end"):
            from apps.tenants.selectors import tenant_timezone

            period = build_period(
                key="custom",
                start_date=data["start"],
                end_date=data["end"],
                tzinfo=tenant_timezone(self.tenant),
            )
        else:
            from .periods import named_period

            period = named_period(data.get("period", "last_30"), tenant=self.tenant)

        job = queue_report(
            tenant=self.tenant,
            report_type=data["report_type"],
            period=period,
            requested_by=request.user,
        )
        return Response(ReportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
