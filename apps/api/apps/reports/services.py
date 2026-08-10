"""
Report and dashboard services.

Every figure here comes from a database aggregate. Nothing loads a table into
Python to add it up, and nothing asks the browser to compute a metric
(spec §31, §82).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.common.money import quantize_money

from .models import ReportFormat, ReportJob, ReportStatus, ReportType
from .periods import Period, named_period

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.orders.models import Order
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.reports")


@dataclass(frozen=True)
class GeneratedDocument:
    """A rendered file plus the metadata a client needs to fetch it."""

    pk: Any
    filename: str
    download_url: str


def _percentage_change(current: Decimal, previous: Decimal) -> str | None:
    """Period-over-period change. ``None`` when there is no baseline.

    Returning ``None`` rather than 0 or 100 keeps the UI honest: "no data to
    compare" is different from "no change".
    """
    if previous <= 0:
        return None
    return str(quantize_money((current - previous) / previous * 100))


def dashboard_summary(*, tenant: Tenant, period: Period) -> dict[str, Any]:
    """Everything the merchant dashboard shows above the fold."""
    from apps.inventory.services import low_stock_items
    from apps.orders.selectors import (
        category_performance,
        customer_metrics,
        dashboard_counters,
        payment_method_breakdown,
        recent_orders,
        revenue_by_day,
        sales_summary,
        top_products,
    )
    from apps.orders.serializers import OrderListSerializer

    tenant_id = tenant.pk
    summary = sales_summary(tenant_id=tenant_id, start=period.start, end=period.end)

    previous = period.previous()
    previous_summary = sales_summary(tenant_id=tenant_id, start=previous.start, end=previous.end)

    today = named_period("today", tenant=tenant)
    month = named_period("month", tenant=tenant)

    low_stock = low_stock_items(tenant_id, limit=10)

    return {
        "period": {
            "key": period.key,
            "start": period.start_date.isoformat(),
            "end": period.end_date.isoformat(),
            "days": period.days,
        },
        "revenue": {
            "period": summary["gross_revenue"],
            "net": summary["net_revenue"],
            "today": sales_summary(tenant_id=tenant_id, start=today.start, end=today.end)[
                "gross_revenue"
            ],
            "month": sales_summary(tenant_id=tenant_id, start=month.start, end=month.end)[
                "gross_revenue"
            ],
            "change_percentage": _percentage_change(
                Decimal(summary["gross_revenue"]), Decimal(previous_summary["gross_revenue"])
            ),
        },
        "orders": {
            "count": summary["order_count"],
            "cancelled": summary["cancelled_orders"],
            "average_ticket": summary["average_ticket"],
            "units_sold": summary["units_sold"],
            "change_percentage": _percentage_change(
                Decimal(summary["order_count"]), Decimal(previous_summary["order_count"])
            ),
        },
        "counters": dashboard_counters(tenant_id=tenant_id),
        "charts": {
            "revenue_by_day": revenue_by_day(
                tenant_id=tenant_id, start=period.start, end=period.end, tzinfo=period.tzinfo
            ),
            "top_products": top_products(tenant_id=tenant_id, start=period.start, end=period.end),
            "categories": category_performance(
                tenant_id=tenant_id, start=period.start, end=period.end
            ),
            "payment_methods": payment_method_breakdown(
                tenant_id=tenant_id, start=period.start, end=period.end
            ),
        },
        "customers": customer_metrics(tenant_id=tenant_id, start=period.start, end=period.end),
        "recent_orders": OrderListSerializer(
            recent_orders(tenant_id=tenant_id, limit=8), many=True
        ).data,
        "alerts": {
            "low_stock_count": len(low_stock),
            "low_stock": [
                {
                    "product": item.product.name,
                    "sku": item.product.sku,
                    "available": str(item.available_quantity),
                    "threshold": str(item.reorder_threshold),
                }
                for item in low_stock
            ],
        },
    }


def sales_report(*, tenant: Tenant, period: Period) -> dict[str, Any]:
    """The sales report, in the same shape the PDF renderer expects."""
    from apps.orders.selectors import (
        category_performance,
        revenue_by_day,
        sales_summary,
        top_products,
    )

    return {
        "period": {"start": period.start_date.isoformat(), "end": period.end_date.isoformat()},
        "summary": sales_summary(tenant_id=tenant.pk, start=period.start, end=period.end),
        "daily": revenue_by_day(
            tenant_id=tenant.pk, start=period.start, end=period.end, tzinfo=period.tzinfo
        ),
        "products": top_products(tenant_id=tenant.pk, start=period.start, end=period.end, limit=25),
        "categories": category_performance(tenant_id=tenant.pk, start=period.start, end=period.end),
    }


def inventory_report(*, tenant: Tenant) -> dict[str, Any]:
    """Stock value and exposure, valued at cost where cost is known."""
    from django.db.models import DecimalField, Sum, Value
    from django.db.models.functions import Coalesce

    from apps.inventory.models import InventoryItem
    from apps.pricing.models import ProductPrice

    money = DecimalField(max_digits=14, decimal_places=2)
    costs = {
        row["product_id"]: row["cost_price"]
        for row in ProductPrice.objects.filter(
            tenant=tenant, is_active=True, cost_price__isnull=False
        ).values("product_id", "cost_price")
    }

    items = (
        InventoryItem.objects.filter(tenant=tenant, track_stock=True)
        .select_related("product")
        .order_by("product__name")
    )

    stock_value = Decimal("0.00")
    rows: list[dict[str, Any]] = []
    for item in items:
        cost = costs.get(item.product_id)
        value = quantize_money(cost * item.quantity) if cost is not None else None
        if value is not None:
            stock_value += value
        rows.append(
            {
                "product": item.product.name,
                "sku": item.product.sku,
                "quantity": str(item.quantity),
                "reserved": str(item.reserved_quantity),
                "available": str(item.available_quantity),
                "unit_cost": str(cost) if cost is not None else None,
                "stock_value": str(value) if value is not None else None,
                "low_stock": item.is_low_stock,
            }
        )

    from django.db.models import Q

    from apps.inventory.models import MovementType, StockMovement

    losses = StockMovement.objects.filter(
        tenant=tenant, movement_type__in=[MovementType.LOSS, MovementType.EXPIRATION]
    ).aggregate(
        total=Coalesce(
            Sum("quantity", filter=Q(quantity__lt=0)),
            Value(Decimal("0.000"), output_field=money),
        )
    )["total"]

    return {
        "generated_at": timezone.now().isoformat(),
        "total_stock_value": str(stock_value),
        "items_tracked": len(rows),
        "low_stock_count": sum(1 for row in rows if row["low_stock"]),
        "recorded_losses": str(losses or Decimal("0.000")),
        "items": rows,
    }


# =============================================================================
# Document generation
# =============================================================================
def generate_order_receipt(order: Order) -> GeneratedDocument:
    """Render and store a receipt PDF, reusing one already generated."""
    from apps.media.models import Document, DocumentType
    from apps.media.services import asset_url, store_generated_file

    existing = (
        Document.objects.filter(
            tenant_id=order.tenant_id,
            related_type="order_receipt",
            related_id=str(order.pk),
        )
        .select_related("asset")
        .first()
    )

    if existing is not None:
        return GeneratedDocument(
            pk=existing.pk,
            filename=existing.asset.original_filename,
            download_url=asset_url(existing.asset),
        )

    from .pdf import render_order_receipt

    content = render_order_receipt(order)
    filename = f"recibo-{order.number}.pdf"
    asset = store_generated_file(
        tenant=order.tenant,
        content=content,
        filename=filename,
        content_type="application/pdf",
    )
    document = Document.objects.create(
        tenant_id=order.tenant_id,
        asset=asset,
        document_type=DocumentType.RECEIPT,
        title=f"Recibo {order.number}",
        related_type="order_receipt",
        related_id=str(order.pk),
    )
    return GeneratedDocument(pk=document.pk, filename=filename, download_url=asset_url(asset))


def run_report_job(job: ReportJob) -> ReportJob:
    """Execute a queued report and attach the rendered file.

    Called from a Celery task; failures are recorded on the job so the UI can
    show something better than a spinner that never stops.
    """
    from apps.media.services import store_generated_file

    from .pdf import render_financial_report, render_sales_report
    from .periods import build_period

    job.status = ReportStatus.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])

    try:
        from datetime import date

        from apps.tenants.selectors import tenant_timezone

        params = job.parameters or {}
        period = build_period(
            key=params.get("period", "custom"),
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            tzinfo=tenant_timezone(job.tenant),
        )
        start_label = period.start_date.strftime("%d/%m/%Y")
        end_label = period.end_date.strftime("%d/%m/%Y")
        label = f"Período: {start_label} a {end_label}"

        if job.report_type == ReportType.FINANCIAL:
            from apps.finance.services import expense_breakdown, profit_and_loss

            content = render_financial_report(
                tenant=job.tenant,
                period_label=label,
                statement=profit_and_loss(
                    tenant_id=job.tenant_id, start=period.start_date, end=period.end_date
                ),
                expenses=expense_breakdown(
                    tenant_id=job.tenant_id, start=period.start_date, end=period.end_date
                ),
            )
            filename = f"financeiro-{period.start_date}-{period.end_date}.pdf"
        else:
            data = sales_report(tenant=job.tenant, period=period)
            content = render_sales_report(
                tenant=job.tenant,
                period_label=label,
                summary=data["summary"],
                daily=data["daily"],
                products=data["products"],
            )
            filename = f"vendas-{period.start_date}-{period.end_date}.pdf"

        job.asset = store_generated_file(
            tenant=job.tenant,
            content=content,
            filename=filename,
            content_type="application/pdf",
        )
        job.status = ReportStatus.COMPLETED
        job.error_message = ""
    except Exception as exc:
        job.status = ReportStatus.FAILED
        job.error_message = str(exc)[:500]
        logger.exception(
            "report_job_failed", extra={"event": "reports.job_failed", "job_id": str(job.pk)}
        )

    job.completed_at = timezone.now()
    job.save()
    return job


def queue_report(
    *,
    tenant: Tenant,
    report_type: str,
    period: Period,
    requested_by: User | None = None,
    output_format: str = ReportFormat.PDF,
) -> ReportJob:
    """Create a report job and hand it to the worker."""
    job = ReportJob.objects.create(
        tenant=tenant,
        report_type=report_type,
        output_format=output_format,
        parameters={
            "period": period.key,
            "start": period.start_date.isoformat(),
            "end": period.end_date.isoformat(),
        },
        requested_by=requested_by,
    )

    from django.db import transaction

    from .tasks import generate_report

    transaction.on_commit(lambda: generate_report.delay(str(job.pk)))
    return job
