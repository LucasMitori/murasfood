from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseCreateView,
    FinancialAccountViewSet,
    FinancialCategoryViewSet,
    FinancialSummaryView,
    FinancialTransactionViewSet,
    ProfitAndLossView,
)

app_name = "finance"

router = DefaultRouter()
router.register("finance/accounts", FinancialAccountViewSet, basename="financial-account")
router.register("finance/categories", FinancialCategoryViewSet, basename="financial-category")
router.register(
    "finance/transactions", FinancialTransactionViewSet, basename="financial-transaction"
)

urlpatterns = [
    path("finance/expenses/", ExpenseCreateView.as_view(), name="add-expense"),
    path("finance/profit-and-loss/", ProfitAndLossView.as_view(), name="profit-and-loss"),
    path("finance/summary/", FinancialSummaryView.as_view(), name="summary"),
    path("", include(router.urls)),
]
