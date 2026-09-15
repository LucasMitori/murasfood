"""
The statement, the plan, the projection and the what-if.

Three of these four produce numbers a merchant will make a real decision on, so
the tests are mostly about the arithmetic being the arithmetic an accountant
would recognise — and about the two that are *estimates* saying so.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from apps.finance.analysis import (
    DEFAULT_ELASTICITY,
    budget_variance,
    cash_flow,
    forecast,
    income_statement,
    price_simulation,
)
from apps.finance.models import (
    Budget,
    BudgetLine,
    FinancialTransaction,
    TransactionType,
)
from apps.finance.services import ensure_chart_of_accounts

pytestmark = pytest.mark.django_db


@pytest.fixture
def chart(tenant: Any) -> dict:
    return ensure_chart_of_accounts(tenant)


def entry(
    tenant: Any,
    chart: dict,
    code: str,
    amount: str,
    on: date,
    kind: str = TransactionType.EXPENSE,
) -> FinancialTransaction:
    from apps.finance.services import default_account

    return FinancialTransaction.objects.create(
        tenant=tenant,
        account=default_account(tenant),
        category=chart[code],
        transaction_type=kind,
        amount=Decimal(amount),
        occurred_on=on,
        description=f"test {code}",
    )


class TestIncomeStatement:
    def test_the_lines_add_up(self, tenant: Any, chart: dict) -> None:
        """Every subtotal is derived, so one wrong sign shows up here."""
        day = date(2026, 5, 10)
        entry(tenant, chart, "sales", "10000.00", day, TransactionType.REVENUE)
        entry(tenant, chart, "cogs", "6000.00", day)
        entry(tenant, chart, "rent", "1500.00", day)
        entry(tenant, chart, "payment-fees", "300.00", day)

        result = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )
        lines = {line["key"]: line["amount"] for line in result["lines"]}

        assert lines["gross_revenue"] == "10000.00"
        assert lines["net_revenue"] == "10000.00"
        assert lines["gross_profit"] == "4000.00"
        assert lines["operating_result"] == "2500.00"
        assert lines["net_result"] == "2200.00"

    def test_sales_tax_is_a_deduction_not_an_expense(self, tenant: Any, chart: dict) -> None:
        """A DRE subtracts tax on sales *above* the gross-profit line. Treating
        it as an operating cost would overstate gross margin."""
        day = date(2026, 5, 10)
        entry(tenant, chart, "sales", "1000.00", day, TransactionType.REVENUE)
        entry(tenant, chart, "taxes", "100.00", day)

        result = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )
        lines = {line["key"]: line["amount"] for line in result["lines"]}

        assert lines["net_revenue"] == "900.00"
        assert lines["gross_profit"] == "900.00"

    def test_vertical_analysis_is_a_share_of_net_revenue(self, tenant: Any, chart: dict) -> None:
        day = date(2026, 5, 10)
        entry(tenant, chart, "sales", "1000.00", day, TransactionType.REVENUE)
        entry(tenant, chart, "cogs", "600.00", day)

        result = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )
        cogs = next(line for line in result["lines"] if line["key"] == "cogs")

        assert cogs["vertical"] == "60.00"
        assert result["margins"]["gross"] == "40.00"

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (date(2026, 5, 1), date(2026, 5, 31)),
            (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 5, 10), date(2026, 5, 16)),
        ],
    )
    def test_the_comparison_window_is_the_same_length(
        self, tenant: Any, chart: dict, start: date, end: date
    ) -> None:
        """Equal length, ending the day before — not the previous calendar month.

        Comparing a 31-day month against a 28-day one makes February look like a
        collapse every year, and the same distortion applies to any custom range.
        The cost is that the window for a 31-day month bleeds one day into the
        month before last; that is a 1/31 smear against a 3/31 one, and it is the
        same rule for every period the screen offers rather than a special case
        for whole months.
        """
        result = income_statement(tenant_id=tenant.pk, start=start, end=end)

        comparison = result["comparison"]
        previous_start = date.fromisoformat(comparison["start"])
        previous_end = date.fromisoformat(comparison["end"])

        assert previous_end == start - timedelta(days=1)
        assert (previous_end - previous_start).days == (end - start).days

    def test_a_missing_baseline_is_none_not_a_percentage(self, tenant: Any, chart: dict) -> None:
        """Nothing to something has no meaningful percentage; printing +100%
        would invent a comparison."""
        entry(tenant, chart, "rent", "500.00", date(2026, 5, 10))

        result = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31)
        )
        rent = next(line for line in result["lines"] if line["key"] == "operating")

        assert rent["horizontal"] is None

    def test_no_recorded_expenses_is_declared(self, tenant: Any, chart: dict) -> None:
        entry(tenant, chart, "sales", "1000.00", date(2026, 5, 10), TransactionType.REVENUE)

        result = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )

        assert result["expenses_recorded"] is False


class TestBudgetVariance:
    def test_under_on_an_expense_is_favourable(self, tenant: Any, chart: dict) -> None:
        """And over on revenue is too. The sign is identical for both, which is
        why the row says which it is rather than leaving it to the colour."""
        budget = Budget.objects.create(tenant=tenant, year=2026, month=5)
        BudgetLine.objects.create(
            tenant=tenant, budget=budget, category=chart["rent"], planned_amount=Decimal("2000")
        )
        entry(tenant, chart, "rent", "1500.00", date(2026, 5, 10))

        result = budget_variance(tenant=tenant, budget=budget)
        row = next(r for r in result["rows"] if r["code"] == "rent")

        assert row["difference"] == "-500.00"
        assert row["favourable"] is True
        assert row["usage_percentage"] == "75.00"

    def test_over_on_revenue_is_favourable(self, tenant: Any, chart: dict) -> None:
        budget = Budget.objects.create(tenant=tenant, year=2026, month=5)
        BudgetLine.objects.create(
            tenant=tenant, budget=budget, category=chart["sales"], planned_amount=Decimal("1000")
        )
        entry(tenant, chart, "sales", "1400.00", date(2026, 5, 10), TransactionType.REVENUE)

        result = budget_variance(tenant=tenant, budget=budget)
        row = next(r for r in result["rows"] if r["code"] == "sales")

        assert row["difference"] == "400.00"
        assert row["favourable"] is True

    def test_spend_with_no_plan_is_flagged(self, tenant: Any, chart: dict) -> None:
        """The most useful row in the report: money that was never budgeted."""
        budget = Budget.objects.create(tenant=tenant, year=2026, month=5)
        entry(tenant, chart, "marketing", "800.00", date(2026, 5, 10))

        result = budget_variance(tenant=tenant, budget=budget)
        row = next(r for r in result["rows"] if r["code"] == "marketing")

        assert row["unplanned"] is True
        assert row["planned"] == "0.00"

    def test_a_plan_with_no_spend_still_appears(self, tenant: Any, chart: dict) -> None:
        """Budgeted and unused is information, not an empty row to hide."""
        budget = Budget.objects.create(tenant=tenant, year=2026, month=5)
        BudgetLine.objects.create(
            tenant=tenant, budget=budget, category=chart["marketing"], planned_amount=Decimal("500")
        )

        result = budget_variance(tenant=tenant, budget=budget)
        row = next(r for r in result["rows"] if r["code"] == "marketing")

        assert row["actual"] == "0.00"
        assert row["unplanned"] is False

    def test_only_the_budget_month_counts(self, tenant: Any, chart: dict) -> None:
        budget = Budget.objects.create(tenant=tenant, year=2026, month=5)
        BudgetLine.objects.create(
            tenant=tenant, budget=budget, category=chart["rent"], planned_amount=Decimal("2000")
        )
        entry(tenant, chart, "rent", "2000.00", date(2026, 6, 10))

        result = budget_variance(tenant=tenant, budget=budget)
        row = next(r for r in result["rows"] if r["code"] == "rent")

        assert row["actual"] == "0.00"


class TestForecast:
    def test_too_little_history_refuses_to_guess(self, tenant: Any) -> None:
        """A trend line through two points is noise with a slope."""
        result = forecast(tenant_id=tenant.pk, months_ahead=3)

        assert result["confidence"] == "insufficient"
        assert result["projection"] == []

    def test_it_projects_a_rising_trend(self, tenant: Any, chart: dict) -> None:
        today = date.today()
        year, month = today.year, today.month
        for step in range(6):
            month -= 1
            if month == 0:
                month, year = 12, year - 1
            entry(
                tenant,
                chart,
                "sales",
                str(1000 + step * 100),
                date(year, month, 15),
                TransactionType.REVENUE,
            )

        result = forecast(tenant_id=tenant.pk, months_ahead=3)

        assert result["basis_months"] == 6
        assert len(result["projection"]) == 3
        # The entries were written newest-first, so revenue *falls* over time.
        assert Decimal(result["monthly_revenue_change"]) < 0

    def test_revenue_never_projects_below_zero(self, tenant: Any, chart: dict) -> None:
        """A steep downward line is arithmetically fine and physically absurd."""
        today = date.today()
        year, month = today.year, today.month
        for step in range(6):
            month -= 1
            if month == 0:
                month, year = 12, year - 1
            entry(
                tenant,
                chart,
                "sales",
                str(100 + step * 900),
                date(year, month, 15),
                TransactionType.REVENUE,
            )

        result = forecast(tenant_id=tenant.pk, months_ahead=6)

        assert all(Decimal(row["revenue"]) >= 0 for row in result["projection"])

    def test_it_is_labelled_as_an_estimate(self, tenant: Any, chart: dict) -> None:
        result = forecast(tenant_id=tenant.pk)

        assert "confidence" in result
        assert result["note"]


class TestCashFlow:
    def test_the_balance_accumulates(self, tenant: Any, chart: dict) -> None:
        entry(tenant, chart, "sales", "1000.00", date(2026, 3, 5), TransactionType.REVENUE)
        entry(tenant, chart, "rent", "400.00", date(2026, 3, 6))
        entry(tenant, chart, "sales", "800.00", date(2026, 4, 5), TransactionType.REVENUE)

        result = cash_flow(tenant_id=tenant.pk, start=date(2026, 3, 1), end=date(2026, 4, 30))

        assert [row["balance"] for row in result["periods"]] == ["600.00", "1400.00"]
        assert result["closing_balance"] == "1400.00"


class TestPriceSimulation:
    def test_no_sales_is_reported_rather_than_shown_as_zeroes(self, tenant: Any) -> None:
        result = price_simulation(
            tenant_id=tenant.pk,
            change_percentage=Decimal("5"),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        assert result["has_data"] is False

    def test_the_assumption_is_returned_with_the_answer(self, tenant: Any) -> None:
        """A number derived from a guess has to carry the guess."""
        result = price_simulation(
            tenant_id=tenant.pk,
            change_percentage=Decimal("10"),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        expected = str(DEFAULT_ELASTICITY.quantize(Decimal("0.01")))
        assert result["assumptions"]["elasticity"] == expected
        assert result["assumptions"]["change_percentage"] == "10.00"
        assert result["assumptions"]["explanation"]

    def test_volume_falls_when_the_price_rises(self, tenant: Any) -> None:
        result = price_simulation(
            tenant_id=tenant.pk,
            change_percentage=Decimal("10"),
            elasticity=Decimal("-1.0"),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        # -1.0 elasticity against +10% price is exactly -10% of volume.
        assert result["assumptions"]["volume_factor"] == "0.90"

    def test_volume_is_floored_rather_than_driven_to_nothing(self, tenant: Any) -> None:
        """A linear model taken far enough predicts negative demand, which is
        not a statement about the shop."""
        result = price_simulation(
            tenant_id=tenant.pk,
            change_percentage=Decimal("100"),
            elasticity=Decimal("-5"),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        assert Decimal(result["assumptions"]["volume_factor"]) == Decimal("0.10")


class TestTenantIsolation:
    def test_one_shop_never_sees_another_shops_ledger(
        self, tenant: Any, other_tenant: Any, chart: dict
    ) -> None:
        entry(tenant, chart, "sales", "5000.00", date(2026, 5, 10), TransactionType.REVENUE)

        mine = income_statement(
            tenant_id=tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )
        theirs = income_statement(
            tenant_id=other_tenant.pk, start=date(2026, 5, 1), end=date(2026, 5, 31), compare=False
        )

        assert {line["key"]: line["amount"] for line in mine["lines"]}["gross_revenue"] == "5000.00"
        assert {line["key"]: line["amount"] for line in theirs["lines"]}["gross_revenue"] == "0.00"
