"""Finance endpoints."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin
from apps.reports.periods import resolve_period

from .models import (
    Budget,
    BudgetLine,
    FinancialAccount,
    FinancialCategory,
    FinancialTransaction,
)
from .serializers import (
    BudgetSerializer,
    ExpenseCreateSerializer,
    FinancialAccountSerializer,
    FinancialCategorySerializer,
    FinancialTransactionSerializer,
    PriceSimulationSerializer,
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


class BudgetViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Monthly plans. Editable, unlike the ledger they are compared against."""

    serializer_class = BudgetSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["finance.view"],
        "retrieve": ["finance.view"],
        "variance": ["finance.view"],
        "default": ["finance.manage"],
    }
    filterset_fields = ["year", "month", "is_active"]

    def get_queryset(self) -> Any:
        return (
            Budget.objects.for_tenant(self.tenant_id)
            .prefetch_related("lines__category")
            .order_by("-year", "-month")
        )

    @extend_schema(responses={200: dict}, operation_id="finance_budget_variance")
    @action(detail=True, methods=["get"])
    def variance(self, request: Request, pk: str | None = None) -> Response:
        """Planned against actual, for this budget's month."""
        from .analysis import budget_variance

        return Response(budget_variance(tenant=self.tenant, budget=self.get_object()))

    @extend_schema(
        request=None, responses={201: BudgetSerializer}, operation_id="finance_budget_copy"
    )
    @action(detail=True, methods=["post"], url_path="copy-to-next")
    def copy_to_next(self, request: Request, pk: str | None = None) -> Response:
        """Start next month from this month's plan.

        Most months look like the month before. Retyping twelve categories to
        change two of them is the reason budgets stop being maintained after
        March.
        """
        source = self.get_object()
        if source.month == 12:
            year, month = source.year + 1, 1
        else:
            year, month = source.year, source.month + 1

        if Budget.objects.for_tenant(self.tenant_id).filter(year=year, month=month).exists():
            raise ValidationError({"detail": _("A budget for that month already exists.")})

        with transaction.atomic():
            copy = Budget.objects.create(
                tenant=self.tenant,
                name=source.name,
                year=year,
                month=month,
                note=source.note,
                created_by=request.user,
            )
            BudgetLine.objects.bulk_create(
                [
                    BudgetLine(
                        tenant=self.tenant,
                        budget=copy,
                        category=line.category,
                        planned_amount=line.planned_amount,
                        note=line.note,
                    )
                    for line in source.lines.all()
                ]
            )

        return Response(BudgetSerializer(copy).data, status=status.HTTP_201_CREATED)


class IncomeStatementView(TenantScopedMixin, APIView):
    """DRE for a period, with vertical and horizontal analysis."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(
        parameters=[
            OpenApiParameter("period", str, description="today|last_7|last_30|month|custom"),
            OpenApiParameter("start", str),
            OpenApiParameter("end", str),
            OpenApiParameter("compare", bool, description="Include the previous period."),
        ],
        responses={200: dict},
        operation_id="finance_income_statement",
    )
    def get(self, request: Request) -> Response:
        from .analysis import income_statement

        window = resolve_period(request, tenant=self.tenant)
        compare = str(request.query_params.get("compare", "true")).lower() != "false"

        return Response(
            income_statement(
                tenant_id=self.tenant_id,
                start=window.start_date,
                end=window.end_date,
                compare=compare,
            )
        )


class ForecastView(TenantScopedMixin, APIView):
    """A straight-line projection of revenue and expenses. Not a promise."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(
        parameters=[
            OpenApiParameter("months", int, description="Months ahead, 1-12. Defaults to 3."),
            OpenApiParameter("history", int, description="Months of history to fit. Default 12."),
        ],
        responses={200: dict},
        operation_id="finance_forecast",
    )
    def get(self, request: Request) -> Response:
        from .analysis import forecast

        def as_int(name: str, fallback: int) -> int:
            try:
                return int(request.query_params.get(name, fallback))
            except (TypeError, ValueError):
                return fallback

        return Response(
            forecast(
                tenant_id=self.tenant_id,
                months_ahead=as_int("months", 3),
                history_months=max(3, min(as_int("history", 12), 36)),
            )
        )


class CashFlowView(TenantScopedMixin, APIView):
    """Money in and out per month, with a running balance.

    Separate from the statement on purpose: that one answers "did the shop make
    money", this one answers "did the shop have money", and a business can fail
    the second while passing the first.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(responses={200: dict}, operation_id="finance_cash_flow")
    def get(self, request: Request) -> Response:
        from .analysis import cash_flow

        window = resolve_period(request, tenant=self.tenant)
        return Response(
            cash_flow(tenant_id=self.tenant_id, start=window.start_date, end=window.end_date)
        )


class PriceSimulationView(TenantScopedMixin, APIView):
    """Replay the period's real sales at a different price.

    A POST because it takes a body of assumptions, not because it writes
    anything — nothing here touches the database beyond reading orders.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["finance.view"]

    @extend_schema(
        request=PriceSimulationSerializer,
        responses={200: dict},
        operation_id="finance_price_simulation",
    )
    def post(self, request: Request) -> Response:
        from .analysis import price_simulation

        payload = PriceSimulationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        window = resolve_period(request, tenant=self.tenant)
        return Response(
            price_simulation(
                tenant_id=self.tenant_id,
                change_percentage=payload.validated_data["change_percentage"],
                elasticity=payload.validated_data.get("elasticity"),
                category_id=payload.validated_data.get("category"),
                start=window.start_date,
                end=window.end_date,
            )
        )
