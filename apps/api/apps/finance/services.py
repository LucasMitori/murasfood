"""
Financial services.

Two responsibilities:

* projecting sales into the ledger (revenue, COGS, payment fees),
* computing a profit-and-loss statement.

The vocabulary is kept strict on purpose (spec §85): revenue is not profit, and
gross profit is not net result. Every figure the API returns names exactly what
it is.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from apps.common.money import money_str, quantize_money

from .models import (
    DEFAULT_CATEGORIES,
    AccountType,
    CategoryKind,
    FinancialAccount,
    FinancialCategory,
    FinancialTransaction,
    TransactionStatus,
    TransactionType,
)

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.orders.models import Order
    from apps.payments.models import Payment
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.finance")

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO_EXPR = Value(Decimal("0.00"), output_field=MONEY)
ZERO = Decimal("0.00")


def ensure_chart_of_accounts(tenant: Tenant) -> dict[str, FinancialCategory]:
    """Create the default account and categories. Idempotent."""
    FinancialAccount.objects.get_or_create(
        tenant=tenant,
        is_default=True,
        defaults={"name": "Conta principal", "account_type": AccountType.BANK},
    )

    categories: dict[str, FinancialCategory] = {}
    for code, name, kind in DEFAULT_CATEGORIES:
        category, _created = FinancialCategory.objects.get_or_create(
            tenant=tenant, code=code, defaults={"name": name, "kind": kind}
        )
        categories[code] = category
    return categories


def default_account(tenant: Tenant) -> FinancialAccount:
    account = FinancialAccount.objects.filter(tenant=tenant, is_default=True).first()
    if account is None:
        ensure_chart_of_accounts(tenant)
        account = FinancialAccount.objects.filter(tenant=tenant, is_default=True).first()
    return account  # type: ignore[return-value]


def _category(tenant: Tenant, code: str) -> FinancialCategory:
    category = FinancialCategory.objects.filter(tenant=tenant, code=code).first()
    if category is None:
        ensure_chart_of_accounts(tenant)
        category = FinancialCategory.objects.filter(tenant=tenant, code=code).first()
    return category  # type: ignore[return-value]


def _record(
    *,
    tenant: Tenant,
    category_code: str,
    transaction_type: str,
    amount: Decimal,
    occurred_on: date,
    description: str,
    reference_type: str = "",
    reference_id: str = "",
    created_by: User | None = None,
) -> FinancialTransaction | None:
    """Write one ledger entry, ignoring duplicates for the same reference."""
    amount = quantize_money(amount)
    if amount <= 0:
        return None

    try:
        with transaction.atomic():
            return FinancialTransaction.objects.create(
                tenant=tenant,
                account=default_account(tenant),
                category=_category(tenant, category_code),
                transaction_type=transaction_type,
                amount=amount,
                occurred_on=occurred_on,
                description=description[:255],
                reference_type=reference_type[:32],
                reference_id=str(reference_id)[:64],
                created_by=created_by,
            )
    except IntegrityError:
        # The unique constraint already holds an entry for this reference and
        # category — the projection has run before.
        return None


@transaction.atomic
def project_order_to_ledger(order: Order) -> list[FinancialTransaction]:
    """Record the financial consequences of a paid order.

    Three entries, because they answer three different questions:

    * **sales** — what the customer paid for goods,
    * **delivery income** — what they paid to receive them,
    * **COGS** — what those goods cost us, from the per-line cost snapshots.

    Safe to call repeatedly; the unique constraint keeps it idempotent.
    """
    from apps.tenants.selectors import tenant_timezone

    if order.paid_at is None:
        return []

    # The business date is the tenant's local date, not the server's (spec §86).
    business_date = order.paid_at.astimezone(tenant_timezone(order.tenant)).date()
    entries: list[FinancialTransaction | None] = [
        _record(
            tenant=order.tenant,
            category_code="sales",
            transaction_type=TransactionType.REVENUE,
            amount=order.subtotal - order.discount_total,
            occurred_on=business_date,
            description=f"Venda {order.number}",
            reference_type="order",
            reference_id=str(order.pk),
        ),
        _record(
            tenant=order.tenant,
            category_code="delivery-income",
            transaction_type=TransactionType.REVENUE,
            amount=order.delivery_fee,
            occurred_on=business_date,
            description=f"Entrega {order.number}",
            reference_type="order",
            reference_id=str(order.pk),
        ),
        _record(
            tenant=order.tenant,
            category_code="cogs",
            transaction_type=TransactionType.EXPENSE,
            amount=order.cost_total,
            occurred_on=business_date,
            description=f"Custo {order.number}",
            reference_type="order",
            reference_id=str(order.pk),
        ),
    ]
    return [entry for entry in entries if entry is not None]


def project_payment_fee(payment: Payment) -> FinancialTransaction | None:
    """Record the acquirer's cut, which is a real cost of every sale."""
    from apps.tenants.selectors import tenant_timezone

    if payment.fee_amount <= 0 or payment.paid_at is None:
        return None

    business_date = payment.paid_at.astimezone(tenant_timezone(payment.tenant)).date()
    return _record(
        tenant=payment.tenant,
        category_code="payment-fees",
        transaction_type=TransactionType.EXPENSE,
        amount=payment.fee_amount,
        occurred_on=business_date,
        description=f"Taxa {payment.provider} — {payment.order.number}",
        reference_type="payment",
        reference_id=str(payment.pk),
    )


def record_expense(
    *,
    tenant: Tenant,
    category_code: str,
    amount: Decimal,
    occurred_on: date,
    description: str,
    created_by: User | None = None,
) -> FinancialTransaction | None:
    """Record a manually entered expense."""
    return _record(
        tenant=tenant,
        category_code=category_code,
        transaction_type=TransactionType.EXPENSE,
        amount=amount,
        occurred_on=occurred_on,
        description=description,
        created_by=created_by,
    )


# =============================================================================
# Reporting
# =============================================================================
def _sum_by_kind(*, tenant_id: Any, start: date, end: date) -> dict[str, Decimal]:
    """Total settled amount per category kind in a period."""
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


def profit_and_loss(*, tenant_id: Any, start: date, end: date) -> dict[str, Any]:
    """A profit-and-loss statement for a period.

    Every line is named for exactly what it contains. ``net_result`` is only
    meaningful when the merchant actually records their expenses, which
    ``expenses_recorded`` makes explicit rather than implying a precision the
    data does not have.
    """
    totals = _sum_by_kind(tenant_id=tenant_id, start=start, end=end)

    sales = totals.get(CategoryKind.SALES, ZERO)
    other_revenue = totals.get(CategoryKind.OTHER_REVENUE, ZERO)
    cogs = totals.get(CategoryKind.COGS, ZERO)
    payment_fees = totals.get(CategoryKind.PAYMENT_FEE, ZERO)
    delivery_costs = totals.get(CategoryKind.DELIVERY_COST, ZERO)
    operating = totals.get(CategoryKind.OPERATING_EXPENSE, ZERO)
    taxes = totals.get(CategoryKind.TAX, ZERO)

    revenue = quantize_money(sales + other_revenue)
    gross_profit = quantize_money(revenue - cogs)
    total_expenses = quantize_money(payment_fees + delivery_costs + operating + taxes)
    net_result = quantize_money(gross_profit - total_expenses)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "revenue": money_str(revenue),
        "sales_revenue": money_str(sales),
        "other_revenue": money_str(other_revenue),
        "cogs": money_str(cogs),
        "gross_profit": money_str(gross_profit),
        "gross_margin_percentage": money_str(gross_profit / revenue * 100 if revenue > 0 else ZERO),
        "payment_fees": money_str(payment_fees),
        "delivery_costs": money_str(delivery_costs),
        "operating_expenses": money_str(operating),
        "taxes": money_str(taxes),
        "total_expenses": money_str(total_expenses),
        "net_result": money_str(net_result),
        "expenses_recorded": bool(operating or taxes),
    }


def monthly_series(*, tenant_id: Any, start: date, end: date) -> list[dict[str, Any]]:
    """Revenue and expenses per month, for the finance chart."""
    rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .annotate(month=TruncMonth("occurred_on"))
        .values("month")
        .annotate(
            revenue=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.REVENUE)), ZERO_EXPR
            ),
            expenses=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)), ZERO_EXPR
            ),
        )
        .order_by("month")
    )
    return [
        {
            "month": row["month"].isoformat() if row["month"] else None,
            "revenue": money_str(row["revenue"]),
            "expenses": money_str(row["expenses"]),
            "result": money_str(row["revenue"] - row["expenses"]),
        }
        for row in rows
    ]


def expense_breakdown(*, tenant_id: Any, start: date, end: date) -> list[dict[str, Any]]:
    """Expenses grouped by category, largest first."""
    rows = (
        FinancialTransaction.objects.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status=TransactionStatus.SETTLED,
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category__name", "category__code", "category__kind")
        .annotate(total=Coalesce(Sum("amount"), ZERO_EXPR))
        .order_by("-total")
    )
    return [
        {
            "category": row["category__name"],
            "code": row["category__code"],
            "kind": row["category__kind"],
            "total": money_str(row["total"]),
        }
        for row in rows
    ]


def soft_delete_transaction(
    entry: FinancialTransaction, *, actor: User | None = None
) -> FinancialTransaction:
    """Void a ledger entry without erasing it (invariant #9)."""
    from django.utils import timezone

    from apps.audit.services import record_audit

    entry.deleted_at = timezone.now()
    entry.status = TransactionStatus.CANCELLED
    entry.save(update_fields=["deleted_at", "status", "updated_at"])

    record_audit(
        action="finance.transaction_voided",
        tenant=entry.tenant,
        actor=actor,
        resource=entry,
        old_values={"amount": str(entry.amount), "description": entry.description},
    )
    return entry
