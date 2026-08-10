"""Report background jobs."""

from __future__ import annotations

import logging

from celery import shared_task

from .models import ReportJob

logger = logging.getLogger("murasfood.reports")


@shared_task(name="apps.reports.tasks.generate_report")
def generate_report(job_id: str) -> str:
    """Render a queued report."""
    from .services import run_report_job

    job = ReportJob.objects.select_related("tenant").filter(pk=job_id).first()
    if job is None:
        return "missing"
    return run_report_job(job).status


@shared_task(name="apps.reports.tasks.project_paid_orders_to_ledger")
def project_paid_orders_to_ledger(limit: int = 200) -> int:
    """Mirror paid orders into the financial ledger.

    Runs on a schedule rather than inline at payment time so a ledger hiccup can
    never fail a customer's checkout. Projection is idempotent, so re-running it
    is always safe.
    """
    from apps.finance.services import project_order_to_ledger, project_payment_fee
    from apps.orders.constants import REVENUE_STATUSES
    from apps.orders.models import Order
    from apps.payments.constants import PaymentStatus
    from apps.payments.models import Payment

    orders = (
        Order.objects.filter(status__in=REVENUE_STATUSES, paid_at__isnull=False)
        .select_related("tenant")
        .prefetch_related("items")
        .order_by("-paid_at")[:limit]
    )

    projected = 0
    for order in orders:
        projected += len(project_order_to_ledger(order))

    for payment in (
        Payment.objects.filter(status=PaymentStatus.PAID, fee_amount__gt=0, paid_at__isnull=False)
        .select_related("tenant", "order")
        .order_by("-paid_at")[:limit]
    ):
        if project_payment_fee(payment) is not None:
            projected += 1

    if projected:
        logger.info(
            "ledger_projection_complete",
            extra={"event": "reports.ledger_projected", "entries": projected},
        )
    return projected


@shared_task(name="apps.reports.tasks.cleanup_old_report_jobs")
def cleanup_old_report_jobs(retention_days: int = 30) -> int:
    """Delete generated report files past the retention window."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.media.services import delete_asset

    cutoff = timezone.now() - timedelta(days=retention_days)
    removed = 0
    for job in ReportJob.objects.filter(created_at__lt=cutoff).select_related("asset"):
        if job.asset is not None:
            delete_asset(job.asset)
        job.delete()
        removed += 1
    return removed
