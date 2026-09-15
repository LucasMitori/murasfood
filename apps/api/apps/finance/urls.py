from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BudgetViewSet,
    CashFlowView,
    ExpenseCreateView,
    FinancialAccountViewSet,
    FinancialCategoryViewSet,
    FinancialSummaryView,
    FinancialTransactionViewSet,
    ForecastView,
    IncomeStatementView,
    PriceSimulationView,
    ProfitAndLossView,
)

app_name = "finance"

router = DefaultRouter()
router.register("finance/accounts", FinancialAccountViewSet, basename="financial-account")
router.register("finance/categories", FinancialCategoryViewSet, basename="financial-category")
router.register(
    "finance/transactions", FinancialTransactionViewSet, basename="financial-transaction"
)
router.register("finance/budgets", BudgetViewSet, basename="budget")

urlpatterns = [
    path("finance/expenses/", ExpenseCreateView.as_view(), name="add-expense"),
    path("finance/profit-and-loss/", ProfitAndLossView.as_view(), name="profit-and-loss"),
    path("finance/summary/", FinancialSummaryView.as_view(), name="summary"),
    path("finance/statement/", IncomeStatementView.as_view(), name="income-statement"),
    path("finance/forecast/", ForecastView.as_view(), name="forecast"),
    path("finance/cash-flow/", CashFlowView.as_view(), name="cash-flow"),
    path("finance/price-simulation/", PriceSimulationView.as_view(), name="price-simulation"),
    path("", include(router.urls)),
]
