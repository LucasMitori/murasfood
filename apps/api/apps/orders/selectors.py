"""Order read queries and aggregates.

Everything here aggregates **in the database**. Loading orders into Python to
add up revenue is the pattern spec §82 forbids, and it stops working at exactly
the point a merchant starts caring about the numbers.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import Avg, Count, DecimalField, F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncDate

from apps.common.money import money_str, quantize_quantity

from .constants import REVENUE_STATUSES, TIMELINE_STEPS, OrderStatus
from .models import Order, OrderItem

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)


def orders_for_customer(*, tenant_id: Any, customer: User) -> QuerySet[Order]:
    return (
        Order.objects.filter(tenant_id=tenant_id, customer=customer)
        .exclude(status=OrderStatus.DRAFT)
        .prefetch_related("items", "payments")
        .select_related("address")
        .order_by("-created_at")
    )


def revenue_queryset(
    *, tenant_id: Any, start: datetime | None = None, end: datetime | None = None
) -> QuerySet[Order]:
    """Orders that count as revenue in a window.

    Filtered on ``placed_at`` rather than ``created_at`` so a draft that sat
    around before checkout lands in the period it was actually placed.
    """
    queryset = Order.objects.filter(tenant_id=tenant_id, status__in=REVENUE_STATUSES)
    if start is not None:
        queryset = queryset.filter(placed_at__gte=start)
    if end is not None:
        queryset = queryset.filter(placed_at__lte=end)
    return queryset


def sales_summary(
    *, tenant_id: Any, start: datetime | None = None, end: datetime | None = None
) -> dict[str, Any]:
    """Headline sales metrics for a period.

    "Revenue" here is gross order value net of refunds — never labelled profit
    (spec §29).
    """
    queryset = revenue_queryset(tenant_id=tenant_id, start=start, end=end)

    aggregates = queryset.aggregate(
        gross_revenue=Coalesce(Sum("total"), ZERO),
        refunded=Coalesce(Sum("refunded_total"), ZERO),
        discounts=Coalesce(Sum("discount_total"), ZERO),
        delivery_income=Coalesce(Sum("delivery_fee"), ZERO),
        order_count=Count("id"),
        average_ticket=Coalesce(Avg("total"), ZERO),
    )

    cancelled = Order.objects.filter(tenant_id=tenant_id, status=OrderStatus.CANCELLED)
    if start is not None:
        cancelled = cancelled.filter(created_at__gte=start)
    if end is not None:
        cancelled = cancelled.filter(created_at__lte=end)

    units = OrderItem.objects.filter(order__in=queryset).aggregate(
        units=Coalesce(Sum("quantity"), Value(Decimal("0.000"), output_field=MONEY))
    )

    gross = aggregates["gross_revenue"]
    refunded = aggregates["refunded"]

    return {
        "gross_revenue": money_str(gross),
        "net_revenue": money_str(gross - refunded),
        "refunded_amount": money_str(refunded),
        "discount_total": money_str(aggregates["discounts"]),
        "delivery_income": money_str(aggregates["delivery_income"]),
        "order_count": aggregates["order_count"],
        "cancelled_orders": cancelled.count(),
        "average_ticket": money_str(aggregates["average_ticket"]),
        "units_sold": f"{quantize_quantity(units['units'])}",
    }


def revenue_by_day(
    *, tenant_id: Any, start: datetime, end: datetime, tzinfo: Any = None
) -> list[dict[str, Any]]:
    """Daily revenue series for the dashboard chart.

    ``TruncDate`` is given the tenant's timezone so a 23:30 sale belongs to the
    correct business day (spec §86).
    """
    rows = (
        revenue_queryset(tenant_id=tenant_id, start=start, end=end)
        .annotate(day=TruncDate("placed_at", tzinfo=tzinfo))
        .values("day")
        .annotate(
            revenue=Coalesce(Sum("total"), ZERO),
            orders=Count("id"),
            average_ticket=Coalesce(Avg("total"), ZERO),
        )
        .order_by("day")
    )
    return [
        {
            "date": row["day"].isoformat() if row["day"] else None,
            "revenue": money_str(row["revenue"]),
            "orders": row["orders"],
            "average_ticket": money_str(row["average_ticket"]),
        }
        for row in rows
    ]


def top_products(
    *, tenant_id: Any, start: datetime | None = None, end: datetime | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    """Best sellers by revenue, with margin where cost is known."""
    orders = revenue_queryset(tenant_id=tenant_id, start=start, end=end)
    rows = (
        OrderItem.objects.filter(order__in=orders)
        .values("product_id", "product_name", "product_sku")
        .annotate(
            units=Coalesce(Sum("quantity"), Value(Decimal("0.000"), output_field=MONEY)),
            revenue=Coalesce(Sum("line_total"), ZERO),
            cost=Coalesce(Sum(F("unit_cost") * F("quantity"), output_field=MONEY), ZERO),
        )
        .order_by("-revenue")[:limit]
    )
    return [
        {
            "product_id": str(row["product_id"]) if row["product_id"] else None,
            "name": row["product_name"],
            "sku": row["product_sku"],
            "units": f"{quantize_quantity(row['units'])}",
            "revenue": money_str(row["revenue"]),
            "estimated_margin": money_str(row["revenue"] - row["cost"]),
        }
        for row in rows
    ]


def category_performance(
    *, tenant_id: Any, start: datetime | None = None, end: datetime | None = None
) -> list[dict[str, Any]]:
    orders = revenue_queryset(tenant_id=tenant_id, start=start, end=end)
    rows = (
        OrderItem.objects.filter(order__in=orders)
        .values("category_name")
        .annotate(revenue=Coalesce(Sum("line_total"), ZERO), units=Coalesce(Sum("quantity"), ZERO))
        .order_by("-revenue")
    )
    return [
        {
            "category": row["category_name"] or "—",
            "revenue": money_str(row["revenue"]),
            "units": f"{quantize_quantity(row['units'])}",
        }
        for row in rows
    ]


def product_sales_totals(*, tenant_id: Any) -> dict[Any, dict[str, Any]]:
    """``product_id -> {units, revenue}`` for the margin analysis table."""
    rows = (
        OrderItem.objects.filter(
            tenant_id=tenant_id, order__status__in=REVENUE_STATUSES, product__isnull=False
        )
        .values("product_id")
        .annotate(units=Coalesce(Sum("quantity"), ZERO), revenue=Coalesce(Sum("line_total"), ZERO))
    )
    return {row["product_id"]: {"units": row["units"], "revenue": row["revenue"]} for row in rows}


def customer_order_stats(*, tenant_id: Any, customer: User) -> dict[str, Any]:
    """Lifetime value summary shown on the customer detail page."""
    queryset = revenue_queryset(tenant_id=tenant_id).filter(customer=customer)
    aggregates = queryset.aggregate(
        total_spent=Coalesce(Sum("total"), ZERO),
        order_count=Count("id"),
        average_ticket=Coalesce(Avg("total"), ZERO),
    )
    last_order = queryset.order_by("-placed_at").first()
    return {
        "total_spent": money_str(aggregates["total_spent"]),
        "order_count": aggregates["order_count"],
        "average_ticket": money_str(aggregates["average_ticket"]),
        "last_order_at": last_order.placed_at.isoformat()
        if last_order and last_order.placed_at
        else None,
        "last_order_number": last_order.number if last_order else None,
    }


def customer_metrics(*, tenant_id: Any, start: datetime, end: datetime) -> dict[str, Any]:
    """New vs returning customers in a window."""
    from apps.accounts.constants import UserType
    from apps.accounts.models import User as UserModel

    new_customers = UserModel.objects.filter(
        tenant_id=tenant_id,
        user_type=UserType.CUSTOMER,
        created_at__gte=start,
        created_at__lte=end,
    ).count()

    buyers = (
        revenue_queryset(tenant_id=tenant_id, start=start, end=end)
        .exclude(customer__isnull=True)
        .values("customer_id")
        .annotate(orders=Count("id"))
    )
    buyer_list = list(buyers)
    repeat = sum(1 for row in buyer_list if row["orders"] > 1)

    return {
        "new_customers": new_customers,
        "active_customers": len(buyer_list),
        "repeat_customers": repeat,
        "repeat_rate": (str(round(repeat / len(buyer_list) * 100, 2)) if buyer_list else "0.00"),
    }


def payment_method_breakdown(
    *, tenant_id: Any, start: datetime | None = None, end: datetime | None = None
) -> list[dict[str, Any]]:
    from apps.payments.constants import PaymentStatus
    from apps.payments.models import Payment

    queryset = Payment.objects.filter(tenant_id=tenant_id, status=PaymentStatus.PAID)
    if start is not None:
        queryset = queryset.filter(paid_at__gte=start)
    if end is not None:
        queryset = queryset.filter(paid_at__lte=end)

    rows = (
        queryset.values("method")
        .annotate(total=Coalesce(Sum("amount"), ZERO), count=Count("id"))
        .order_by("-total")
    )
    return [
        {"method": row["method"], "total": money_str(row["total"]), "count": row["count"]}
        for row in rows
    ]


def order_timeline(order: Order) -> list[dict[str, Any]]:
    """Customer-facing progress timeline, built from recorded history.

    Steps come from the backend, never from the client guessing what "probably"
    happened (spec §94).
    """
    history = {
        entry.new_status: entry for entry in order.status_history.all() if entry.is_customer_visible
    }

    # A pickup order never goes out for delivery, and vice versa: showing both
    # branches would leave one step permanently greyed out.
    skipped = (
        {OrderStatus.OUT_FOR_DELIVERY}
        if order.delivery_method == "PICKUP"
        else {OrderStatus.READY_FOR_PICKUP}
    )
    relevant = [(status, label) for status, label in TIMELINE_STEPS if status not in skipped]

    timeline: list[dict[str, Any]] = []
    for status, label_key in relevant:
        entry = history.get(status)
        timeline.append(
            {
                "status": status,
                "label_key": label_key,
                "completed": entry is not None,
                "timestamp": entry.created_at.isoformat() if entry else None,
                "reason": entry.reason if entry else "",
            }
        )
    return timeline


def dashboard_counters(*, tenant_id: Any) -> dict[str, int]:
    """Counts that drive the badges on the merchant dashboard."""
    from apps.payments.constants import PaymentStatus
    from apps.payments.models import Payment

    return {
        "pending_orders": Order.objects.filter(
            tenant_id=tenant_id,
            status__in=[OrderStatus.PAID, OrderStatus.CONFIRMED, OrderStatus.PREPARING],
        ).count(),
        "awaiting_payment": Order.objects.filter(
            tenant_id=tenant_id, status=OrderStatus.PENDING_PAYMENT
        ).count(),
        "ready_orders": Order.objects.filter(
            tenant_id=tenant_id,
            status__in=[OrderStatus.READY_FOR_PICKUP, OrderStatus.OUT_FOR_DELIVERY],
        ).count(),
        "pending_payments": Payment.objects.filter(
            tenant_id=tenant_id, status__in=[PaymentStatus.PENDING, PaymentStatus.PROCESSING]
        ).count(),
    }


def recent_orders(*, tenant_id: Any, limit: int = 10) -> QuerySet[Order]:
    return (
        Order.objects.filter(tenant_id=tenant_id)
        .exclude(status=OrderStatus.DRAFT)
        .select_related("customer")
        .order_by("-created_at")[:limit]
    )


def orders_needing_attention(*, tenant_id: Any) -> QuerySet[Order]:
    """Paid orders nobody has started preparing yet."""
    return (
        Order.objects.filter(
            tenant_id=tenant_id, status__in=[OrderStatus.PAID, OrderStatus.CONFIRMED]
        )
        .select_related("customer")
        .order_by("placed_at")
    )


def search_orders(queryset: QuerySet[Order], term: str) -> QuerySet[Order]:
    """Find an order by number, customer name, email or phone."""
    term = (term or "").strip()
    if not term:
        return queryset
    return queryset.filter(
        Q(number__icontains=term)
        | Q(customer_name__icontains=term)
        | Q(customer_email__icontains=term)
        | Q(customer_phone__icontains=term)
    )
