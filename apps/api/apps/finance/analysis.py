"""
Financial analysis: the statement, the plan, the projection and the what-if.

Everything here reads the one ledger that :mod:`apps.finance.services` writes.
Nothing in this module creates a transaction, and nothing recomputes a figure
that ``profit_and_loss`` already produces — two implementations of "revenue"
eventually disagree, and the one on screen is never the one someone checked.

A note on honesty, because three of the four things here are estimates:

* the **statement** is a fact — it is arithmetic over recorded rows;
* the **variance** is a fact about a plan someone typed;
* the **forecast** is an extrapolation, and says so, with the number of months
  it was derived from attached so a merchant can judge it;
* the **price simulation** rests on an elasticity assumption the merchant
  chooses, and is returned with that assumption echoed back.

Presenting the last two with the same confidence as the first would be the most
damaging thing this module could do. A shop owner deciding whether to raise
prices on the strength of a number needs to know which kind of number it is.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from apps.common.money import money_str, quantize_money

from .models import (
    Budget,
    CategoryKind,
    FinancialTransaction,
    TransactionStatus,
    TransactionType,
)

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO_EXPR = Value(Decimal("0.00"), output_field=MONEY)
ZERO = Decimal("0.00")

#: Below this many months of history, a trend line is noise with a slope.
MIN_MONTHS_FOR_TREND = 3

#: How far ahead a projection stays worth printing. Beyond a quarter, a linear
#: fit on a small shop's history says more about the fit than about the shop.
MAX_FORECAST_MONTHS = 12

#: Default price elasticity of demand: a 1% price rise costs 0.8% of volume.
#:
#: Groceries sit between roughly -0.3 (staples people buy regardless) and -2.0
#: (treats with an obvious substitute on the next shelf). -0.8 is a defensible
#: middle for a mixed basket, and it is only ever a starting value — the caller
#: passes their own, and the response repeats whichever was used.
DEFAULT_ELASTICITY = Decimal("-0.8")


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    """``part`` as a percentage of ``whole``. Zero when there is no whole."""
    if not whole:
        return ZERO
    return quantize_money(part / whole * 100)


def _change(current: Decimal, previous: Decimal) -> Decimal | None:
    """Percentage change, or ``None`` when there is no baseline to compare to.

    ``None`` rather than 0 or 100: going from nothing to something has no
    meaningful percentage, and printing "+100%" for a shop's first month of rent
    would be inventing a comparison that does not exist.
    """
    if not previous:
        return None
    return quantize_money((current - previous) / previous * 100)


# =============================================================================
# DRE — the income statement, in the shape a Brazilian accountant expects
# =============================================================================
@dataclass
class StatementLine:
    """One row of the statement.

    ``vertical`` is the line as a percentage of net revenue (análise vertical);
    ``horizontal`` is the change against the comparison period (análise
    horizontal). Both are what turn a column of numbers into something a
    merchant can read at a glance — "marketing is 4% of revenue and up 60% on
    last month" is a sentence; "R$ 1.240,00" is not.
    """

    key: str
    label: str
    amount: Decimal
    #: Emphasis for the UI: totals are the lines someone actually reads.
    level: str = "item"
    vertical: Decimal = ZERO
    horizontal: Decimal | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "amount": money_str(self.amount),
            "level": self.level,
            "vertical": money_str(self.vertical),
            "horizontal": None if self.horizontal is None else money_str(self.horizontal),
        }


def _totals_by_kind(*, tenant_id: Any, start: date, end: date) -> dict[str, Decimal]:
    """Settled amount per category kind, for one window."""
    rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category__kind")
        .annotate(total=Coalesce(Sum("amount"), ZERO_EXPR))
    )
    return {row["category__kind"]: row["total"] for row in rows}


def _statement_figures(totals: dict[str, Decimal]) -> dict[str, Decimal]:
    """Derive every line of the statement from the per-kind totals.

    Split out so the current period and the comparison period are computed by
    exactly the same code. Doing it twice inline is how a comparison ends up
    subtly measuring something different from the thing it compares to.
    """
    sales = totals.get(CategoryKind.SALES, ZERO)
    other_revenue = totals.get(CategoryKind.OTHER_REVENUE, ZERO)
    cogs = totals.get(CategoryKind.COGS, ZERO)
    payment_fees = totals.get(CategoryKind.PAYMENT_FEE, ZERO)
    delivery = totals.get(CategoryKind.DELIVERY_COST, ZERO)
    operating = totals.get(CategoryKind.OPERATING_EXPENSE, ZERO)
    taxes = totals.get(CategoryKind.TAX, ZERO)

    gross_revenue = sales + other_revenue
    # Taxes on sales are a deduction from gross revenue in a DRE, not an
    # operating expense — which is why they sit above the gross-profit line
    # rather than beside rent.
    net_revenue = gross_revenue - taxes
    gross_profit = net_revenue - cogs
    operating_expenses = operating + delivery
    operating_result = gross_profit - operating_expenses
    net_result = operating_result - payment_fees

    return {
        "gross_revenue": gross_revenue,
        "sales": sales,
        "other_revenue": other_revenue,
        "taxes": taxes,
        "net_revenue": net_revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "operating": operating,
        "delivery": delivery,
        "operating_expenses": operating_expenses,
        "operating_result": operating_result,
        "payment_fees": payment_fees,
        "net_result": net_result,
    }


#: Statement rows, in the order they are read. ``level`` marks the subtotals.
DRE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("gross_revenue", "Receita bruta", "total"),
    ("sales", "Vendas de mercadorias", "item"),
    ("other_revenue", "Outras receitas", "item"),
    ("taxes", "(-) Impostos sobre vendas", "item"),
    ("net_revenue", "= Receita líquida", "subtotal"),
    ("cogs", "(-) Custo das mercadorias vendidas", "item"),
    ("gross_profit", "= Lucro bruto", "subtotal"),
    ("operating", "(-) Despesas operacionais", "item"),
    ("delivery", "(-) Custos de entrega", "item"),
    ("operating_result", "= Resultado operacional", "subtotal"),
    ("payment_fees", "(-) Taxas de pagamento", "item"),
    ("net_result", "= Resultado líquido", "total"),
)


def income_statement(
    *, tenant_id: Any, start: date, end: date, compare: bool = True
) -> dict[str, Any]:
    """A DRE for the period, with vertical and horizontal analysis.

    The comparison period is the same number of days immediately before the one
    requested. Equal length matters: comparing a 31-day month against a 28-day
    one makes February look like a collapse every single year.
    """
    figures = _statement_figures(_totals_by_kind(tenant_id=tenant_id, start=start, end=end))

    previous: dict[str, Decimal] = {}
    span = (end - start).days + 1
    previous_start = start - timedelta(days=span)
    previous_end = start - timedelta(days=1)

    if compare:
        previous = _statement_figures(
            _totals_by_kind(tenant_id=tenant_id, start=previous_start, end=previous_end)
        )

    base = figures["net_revenue"]
    lines = [
        StatementLine(
            key=key,
            label=label,
            amount=figures[key],
            level=level,
            vertical=_pct(figures[key], base),
            horizontal=_change(figures[key], previous[key]) if previous else None,
        )
        for key, label, level in DRE_ROWS
    ]

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "comparison": (
            {"start": previous_start.isoformat(), "end": previous_end.isoformat()}
            if compare
            else None
        ),
        "lines": [line.as_dict() for line in lines],
        "margins": {
            "gross": money_str(_pct(figures["gross_profit"], base)),
            "operating": money_str(_pct(figures["operating_result"], base)),
            "net": money_str(_pct(figures["net_result"], base)),
        },
        # Named for what it is: a shop that records no expenses will see a net
        # result equal to its gross profit, and should not read that as profit.
        "expenses_recorded": bool(figures["operating"] or figures["taxes"]),
    }


# =============================================================================
# Budget versus actual
# =============================================================================
def budget_variance(*, tenant: Tenant, budget: Budget) -> dict[str, Any]:
    """What was planned, what happened, and the gap.

    Sign convention is the thing to get right. For an expense, spending *less*
    than planned is good; for revenue, earning less is bad. Rather than make the
    reader work that out from a minus sign, each row carries ``favourable`` —
    already reasoned about, so the UI colours it without repeating the logic.
    """
    start, end = budget.period

    planned = {line.category_id: line for line in budget.lines.select_related("category").all()}

    actual_rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant.pk,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category_id", "category__name", "category__kind", "category__code")
        .annotate(total=Coalesce(Sum("amount"), ZERO_EXPR))
    )
    actual = {row["category_id"]: row for row in actual_rows}

    revenue_kinds = {CategoryKind.SALES, CategoryKind.OTHER_REVENUE}
    rows: list[dict[str, Any]] = []

    # Every category that appears on either side. A category with a plan and no
    # spend matters (it was budgeted and not used); so does spend with no plan
    # (it was not budgeted at all), and that second case is the one a merchant
    # most needs to see.
    for category_id in {*planned, *actual}:
        line = planned.get(category_id)
        seen = actual.get(category_id)

        plan_amount = line.planned_amount if line else ZERO
        real_amount = seen["total"] if seen else ZERO

        name = line.category.name if line else seen["category__name"]
        kind = line.category.kind if line else seen["category__kind"]
        code = line.category.code if line else seen["category__code"]

        difference = real_amount - plan_amount
        is_revenue = kind in revenue_kinds

        rows.append(
            {
                "category_id": str(category_id),
                "category": name,
                "code": code,
                "kind": kind,
                "planned": money_str(plan_amount),
                "actual": money_str(real_amount),
                "difference": money_str(difference),
                "usage_percentage": money_str(_pct(real_amount, plan_amount)),
                # Over on revenue is good; over on an expense is not.
                "favourable": bool(difference >= 0) if is_revenue else bool(difference <= 0),
                "unplanned": line is None,
            }
        )

    rows.sort(key=lambda row: (row["kind"], row["category"]))

    planned_expense = sum(
        (
            line.planned_amount
            for line in planned.values()
            if line.category.kind not in revenue_kinds
        ),
        ZERO,
    )
    actual_expense = sum(
        (row["total"] for row in actual_rows if row["category__kind"] not in revenue_kinds),
        ZERO,
    )
    planned_revenue = sum(
        (line.planned_amount for line in planned.values() if line.category.kind in revenue_kinds),
        ZERO,
    )
    actual_revenue = sum(
        (row["total"] for row in actual_rows if row["category__kind"] in revenue_kinds),
        ZERO,
    )

    return {
        "budget": {
            "id": str(budget.pk),
            "name": str(budget),
            "year": budget.year,
            "month": budget.month,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
        "rows": rows,
        "summary": {
            "planned_revenue": money_str(planned_revenue),
            "actual_revenue": money_str(actual_revenue),
            "planned_expenses": money_str(planned_expense),
            "actual_expenses": money_str(actual_expense),
            "planned_result": money_str(planned_revenue - planned_expense),
            "actual_result": money_str(actual_revenue - actual_expense),
            "expense_usage_percentage": money_str(_pct(actual_expense, planned_expense)),
        },
    }


# =============================================================================
# Forecast
# =============================================================================
def _monthly_history(*, tenant_id: Any, months: int) -> list[dict[str, Any]]:
    """Revenue and expenses per month over the trailing window."""
    today = date.today()
    first_of_this_month = today.replace(day=1)

    # Walk back `months` whole months. Calendar arithmetic rather than 30-day
    # steps, because a 30-day step drifts and eventually skips February.
    year, month = first_of_this_month.year, first_of_this_month.month
    for _ in range(months):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    start = date(year, month, 1)

    rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            occurred_on__gte=start,
            occurred_on__lt=first_of_this_month,
        )
        .annotate(bucket=TruncMonth("occurred_on"))
        .values("bucket")
        .annotate(
            revenue=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.REVENUE)), ZERO_EXPR
            ),
            expenses=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)), ZERO_EXPR
            ),
        )
        .order_by("bucket")
    )
    return [
        {
            "month": row["bucket"].isoformat(),
            "revenue": row["revenue"],
            "expenses": row["expenses"],
        }
        for row in rows
    ]


def _trend(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Least-squares line through ``values``, as ``(intercept, slope)``.

    Ordinary linear regression on the index. Deliberately the simplest model
    that captures a direction: a shop with eight months of history does not have
    the data to justify anything seasonal, and a more elaborate model would only
    make a guess look authoritative.
    """
    count = len(values)
    if count == 0:
        return ZERO, ZERO
    if count == 1:
        return values[0], ZERO

    n = Decimal(count)
    indices = [Decimal(i) for i in range(count)]
    mean_x = sum(indices, ZERO) / n
    mean_y = sum(values, ZERO) / n

    variance = sum(((x - mean_x) ** 2 for x in indices), ZERO)
    if not variance:
        return mean_y, ZERO

    covariance = sum(
        ((x - mean_x) * (y - mean_y) for x, y in zip(indices, values, strict=True)), ZERO
    )
    slope = covariance / variance
    return mean_y - slope * mean_x, slope


def forecast(*, tenant_id: Any, months_ahead: int = 3, history_months: int = 12) -> dict[str, Any]:
    """Project revenue, expenses and result forward.

    An extrapolation of a straight line through the last ``history_months``
    completed months. Every part of the response is labelled so nobody mistakes
    it for a statement: ``basis`` says how many months it was fitted to, and
    ``confidence`` is deliberately coarse — ``low`` under six months, because a
    projection from four points is a shape, not a prediction.

    The current month is excluded from the fit. A month that is a third over
    would otherwise drag the trend down every time it is read.
    """
    months_ahead = max(1, min(months_ahead, MAX_FORECAST_MONTHS))
    history = _monthly_history(tenant_id=tenant_id, months=history_months)

    if len(history) < MIN_MONTHS_FOR_TREND:
        return {
            "basis_months": len(history),
            "confidence": "insufficient",
            "history": [
                {
                    "month": row["month"],
                    "revenue": money_str(row["revenue"]),
                    "expenses": money_str(row["expenses"]),
                }
                for row in history
            ],
            "projection": [],
            "note": (
                "At least three completed months of records are needed before a "
                "trend means anything."
            ),
        }

    revenue_intercept, revenue_slope = _trend([row["revenue"] for row in history])
    expense_intercept, expense_slope = _trend([row["expenses"] for row in history])

    today = date.today()
    year, month = today.year, today.month

    projection: list[dict[str, Any]] = []
    for step in range(months_ahead):
        index = Decimal(len(history) + step)
        # Negative revenue is arithmetically possible from a downward line and
        # physically meaningless, so the floor is zero.
        revenue = max(ZERO, revenue_intercept + revenue_slope * index)
        expenses = max(ZERO, expense_intercept + expense_slope * index)

        projection.append(
            {
                "month": date(year, month, 1).isoformat(),
                "revenue": money_str(quantize_money(revenue)),
                "expenses": money_str(quantize_money(expenses)),
                "result": money_str(quantize_money(revenue - expenses)),
            }
        )

        month += 1
        if month == 13:
            month, year = 1, year + 1

    confidence = "low" if len(history) < 6 else ("medium" if len(history) < 12 else "good")

    return {
        "basis_months": len(history),
        "confidence": confidence,
        "monthly_revenue_change": money_str(quantize_money(revenue_slope)),
        "monthly_expense_change": money_str(quantize_money(expense_slope)),
        "history": [
            {
                "month": row["month"],
                "revenue": money_str(row["revenue"]),
                "expenses": money_str(row["expenses"]),
            }
            for row in history
        ],
        "projection": projection,
        "note": "A straight-line extrapolation of completed months. Not a guarantee.",
    }


# =============================================================================
# Cash flow
# =============================================================================
def cash_flow(*, tenant_id: Any, start: date, end: date) -> dict[str, Any]:
    """Money in and out per month, with a running balance.

    Distinct from the statement on purpose. The statement answers "did the shop
    make money"; this answers "did the shop *have* money", and a business can
    fail the second while passing the first.
    """
    rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .annotate(bucket=TruncMonth("occurred_on"))
        .values("bucket")
        .annotate(
            inflow=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.REVENUE)), ZERO_EXPR
            ),
            outflow=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)), ZERO_EXPR
            ),
        )
        .order_by("bucket")
    )

    running = ZERO
    periods: list[dict[str, Any]] = []
    for row in rows:
        net = row["inflow"] - row["outflow"]
        running += net
        periods.append(
            {
                "month": row["bucket"].isoformat(),
                "inflow": money_str(row["inflow"]),
                "outflow": money_str(row["outflow"]),
                "net": money_str(net),
                "balance": money_str(running),
            }
        )

    pending = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.PENDING,
        )
        .values("transaction_type")
        .annotate(total=Coalesce(Sum("amount"), ZERO_EXPR))
    )
    committed = {row["transaction_type"]: row["total"] for row in pending}

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "periods": periods,
        "closing_balance": money_str(running),
        # Money already promised in either direction, which is what turns a
        # healthy balance into a misleading one.
        "pending_in": money_str(committed.get(TransactionType.REVENUE, ZERO)),
        "pending_out": money_str(committed.get(TransactionType.EXPENSE, ZERO)),
    }


# =============================================================================
# Price simulation
# =============================================================================
def price_simulation(
    *,
    tenant_id: Any,
    change_percentage: Decimal,
    elasticity: Decimal | None = None,
    start: date,
    end: date,
    category_id: Any = None,
) -> dict[str, Any]:
    """What a price change would have done to the period just gone.

    Answers the question a shop owner actually asks — "if I put everything up
    five per cent, am I better off?" — by replaying real sales at the new price
    and shrinking the volume by the elasticity.

    The honest framing matters more than the arithmetic. This is **not** a
    prediction: it is the last period recomputed under one assumption, and that
    assumption is the merchant's. A 5% rise that keeps every customer is
    arithmetic; the same rise that drives away 4% of volume is a judgement about
    shoppers, and only the shopkeeper knows their shoppers.

    Volume, revenue and cost come from order lines rather than the ledger,
    because the ledger has no units in it and a margin without units cannot be
    re-priced.
    """
    from apps.orders.constants import OrderStatus
    from apps.orders.models import OrderItem

    elasticity = DEFAULT_ELASTICITY if elasticity is None else Decimal(str(elasticity))
    change = Decimal(str(change_percentage)) / Decimal("100")

    items = OrderItem.objects.filter(
        order__tenant_id=tenant_id,
        order__created_at__date__gte=start,
        order__created_at__date__lte=end,
    ).exclude(order__status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])

    if category_id:
        items = items.filter(product__category_id=category_id)

    totals = items.aggregate(
        revenue=Coalesce(Sum(F("unit_price") * F("quantity"), output_field=MONEY), ZERO_EXPR),
        cost=Coalesce(Sum(F("unit_cost") * F("quantity"), output_field=MONEY), ZERO_EXPR),
        units=Coalesce(Sum("quantity"), Value(Decimal("0.000"))),
        lines=Count("id"),
    )

    revenue = quantize_money(totals["revenue"])
    cost = quantize_money(totals["cost"])
    units = totals["units"] or Decimal("0.000")
    margin = revenue - cost

    # Volume responds to the price change by elasticity × the change. Floored at
    # 10% of current volume: an elasticity steep enough to wipe out demand
    # entirely is outside anything this model can speak to, and returning "you
    # would sell nothing" from a linear approximation would be nonsense stated
    # precisely.
    volume_factor = max(Decimal("0.1"), Decimal("1") + elasticity * change)
    price_factor = Decimal("1") + change

    projected_revenue = quantize_money(revenue * price_factor * volume_factor)
    projected_cost = quantize_money(cost * volume_factor)
    projected_margin = projected_revenue - projected_cost

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "assumptions": {
            "change_percentage": money_str(Decimal(str(change_percentage))),
            "elasticity": money_str(elasticity),
            "volume_factor": money_str(quantize_money(volume_factor)),
            "explanation": (
                "Real sales for the period, replayed at the new price with volume "
                "adjusted by the elasticity. An assumption, not a forecast."
            ),
        },
        "current": {
            "revenue": money_str(revenue),
            "cost": money_str(cost),
            "margin": money_str(margin),
            "margin_percentage": money_str(_pct(margin, revenue)),
            "units": str(units),
            "order_lines": totals["lines"],
        },
        "projected": {
            "revenue": money_str(projected_revenue),
            "cost": money_str(projected_cost),
            "margin": money_str(projected_margin),
            "margin_percentage": money_str(_pct(projected_margin, projected_revenue)),
            "units": str(quantize_money(units * volume_factor)),
        },
        "delta": {
            "revenue": money_str(projected_revenue - revenue),
            "margin": money_str(projected_margin - margin),
            "margin_change_percentage": (
                money_str(_change(projected_margin, margin) or ZERO) if margin else None
            ),
        },
        # Without sales in the window there is nothing to replay, and every
        # figure above is zero. Saying so beats showing a table of noughts.
        "has_data": bool(totals["lines"]),
    }


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last day of a month."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)
