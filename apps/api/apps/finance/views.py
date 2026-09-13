"""Finance endpoints."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin
from apps.reports.periods import resolve_period

from .models import FinancialAccount, FinancialCategory, FinancialTransaction
from .serializers import (
    ExpenseCreateSerializer,
    FinancialAccountSerializer,
    FinancialCategorySerializer,
    FinancialTransactionSerializer,
    ProfitAndLossSerializer,
)
from .services import (
    ensure_chart_of_accounts,
    expense_breakdown,
    monthly_series,
    profit_and_loss,
    record_expense,
    soft_delete_transaction,
)


class FinancialAccountViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = FinancialAccountSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["finance.view"], "default": ["finance.manage"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return FinancialAccount.objects.for_tenant(self.tenant_id).order_by("name")


class FinancialCategoryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = FinancialCategorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["finance.view"], "default": ["finance.manage"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return FinancialCategory.objects.for_tenant(self.tenant_id).order_by("kind", "name")

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # A merchant opening the finance screen for the first time should find a
        # usable chart of accounts, not an empty page.
        if not self.get_queryset().exists():
            ensure_chart_of_accounts(self.tenant)
        return super().list(request, *args, **kwargs)


class FinancialTransactionViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = FinancialTransactionSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["finance.view"],
        "retrieve": ["finance.view"],
        "default": ["finance.manage"],
    }
    filterset_fields = ["transaction_type", "category", "account", "status"]
    search_fields = ["description", "note", "reference_id", "category__name"]

    def get_queryset(self) -> Any:
        queryset = (
            FinancialTransaction.objects.for_tenant(self.tenant_id)
            .filter(deleted_at__isnull=True)
            .select_related("category", "account")
            .order_by("-occurred_on", "-created_at")
        )
        params = self.request.query_params
        if params.get("date_from"):
            queryset = queryset.filter(occurred_on__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(occurred_on__lte=params["date_to"])
        return queryset

    def perform_destroy(self, instance: FinancialTransaction) -> None:
        """Void rather than delete — financial records are never removed."""
        soft_delete_transaction(instance, actor=self.request.user)


class ExpenseCreateView(TenantScopedMixin, APIView):
    """Shortcut for the "add an expense" form."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.manage"]

    @extend_schema(
        request=ExpenseCreateSerializer,
        responses={201: FinancialTransactionSerializer},
        operation_id="finance_add_expense",
    )
    def post(self, request: Request) -> Response:
        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry = record_expense(
            tenant=self.tenant, created_by=request.user, **serializer.validated_data
        )
        if entry is None:
            return Response(
                {"detail": "The expense could not be recorded."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(FinancialTransactionSerializer(entry).data, status=status.HTTP_201_CREATED)


class ProfitAndLossView(TenantScopedMixin, APIView):
    """Profit-and-loss statement for a period."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "period",
                str,
                description="today|yesterday|last_7|last_30|month|previous_month|custom",
            ),
            OpenApiParameter("start", str),
            OpenApiParameter("end", str),
        ],
        responses=ProfitAndLossSerializer,
        operation_id="finance_profit_and_loss",
    )
    def get(self, request: Request) -> Response:
        window = resolve_period(request, tenant=self.tenant)
        return Response(
            profit_and_loss(tenant_id=self.tenant_id, start=window.start_date, end=window.end_date)
        )


class FinancialSummaryView(TenantScopedMixin, APIView):
    """P&L plus the series and breakdown the finance dashboard charts."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(responses={200: dict}, operation_id="finance_summary")
    def get(self, request: Request) -> Response:
        window = resolve_period(request, tenant=self.tenant)
        return Response(
            {
                "statement": profit_and_loss(
                    tenant_id=self.tenant_id, start=window.start_date, end=window.end_date
                ),
                "monthly": monthly_series(
                    tenant_id=self.tenant_id, start=window.start_date, end=window.end_date
                ),
                "expenses_by_category": expense_breakdown(
                    tenant_id=self.tenant_id, start=window.start_date, end=window.end_date
                ),
            }
        )
