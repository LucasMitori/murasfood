"""Dashboard aggregates, financial statements and PDF generation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.reports.periods import named_period, resolve_period

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid_order(tenant: Any, customer: Any, filled_cart: Any) -> Any:
    """An order that has been paid, so it counts as revenue."""
    from apps.orders.constants import OrderStatus
    from apps.orders.services import create_order_from_cart, transition_order

    order = create_order_from_cart(
        tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
    )
    return transition_order(order, to_status=OrderStatus.PAID)


class TestPeriods:
    def test_today_is_a_single_day(self, tenant: Any) -> None:
        period = named_period("today", tenant=tenant)
        assert period.days == 1
        assert period.start_date == period.end_date

    def test_last_seven_days_spans_a_week(self, tenant: Any) -> None:
        assert named_period("last_7", tenant=tenant).days == 7

    def test_unknown_key_falls_back_to_last_30(self, tenant: Any) -> None:
        assert named_period("nonsense", tenant=tenant).days == 30

    def test_previous_window_is_the_same_length(self, tenant: Any) -> None:
        period = named_period("last_7", tenant=tenant)
        previous = period.previous()

        assert previous.days == period.days
        assert previous.end_date == period.start_date - timedelta(days=1)

    def test_period_uses_the_tenant_timezone(self, tenant: Any) -> None:
        """A report boundary must follow the merchant's clock, not the server's."""
        period = named_period("today", tenant=tenant)
        assert str(period.tzinfo) == tenant.timezone

    def test_reversed_custom_range_is_corrected(self, tenant: Any) -> None:
        class FakeRequest:
            query_params = {"period": "custom", "start": "2026-03-31", "end": "2026-03-01"}

        period = resolve_period(FakeRequest(), tenant=tenant)
        assert period.start_date < period.end_date

    def test_custom_range_is_capped(self, tenant: Any) -> None:
        class FakeRequest:
            query_params = {"period": "custom", "start": "2000-01-01", "end": "2026-01-01"}

        assert resolve_period(FakeRequest(), tenant=tenant).days <= 731


class TestSalesAggregates:
    def test_paid_order_counts_as_revenue(self, tenant: Any, paid_order: Any) -> None:
        from apps.orders.selectors import sales_summary

        summary = sales_summary(tenant_id=tenant.pk)
        assert summary["gross_revenue"] == "25.00"
        assert summary["order_count"] == 1

    def test_cancelled_order_is_not_revenue(
        self, tenant: Any, customer: Any, filled_cart: Any
    ) -> None:
        from apps.orders.selectors import sales_summary
        from apps.orders.services import cancel_order, create_order_from_cart

        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )
        cancel_order(order, reason="Teste")

        summary = sales_summary(tenant_id=tenant.pk)
        assert summary["gross_revenue"] == "0.00"
        assert summary["cancelled_orders"] == 1

    def test_refunds_reduce_net_revenue_only(self, tenant: Any, paid_order: Any) -> None:
        """Gross stays gross; only the net figure moves (spec §29)."""
        from apps.orders.selectors import sales_summary
        from apps.orders.services import register_refund

        register_refund(paid_order, amount=Decimal("10.00"))

        summary = sales_summary(tenant_id=tenant.pk)
        assert summary["gross_revenue"] == "25.00"
        assert summary["net_revenue"] == "15.00"

    def test_top_products_ranks_by_revenue(self, tenant: Any, paid_order: Any) -> None:
        from apps.orders.selectors import top_products

        rows = top_products(tenant_id=tenant.pk)
        assert rows[0]["revenue"] == "25.00"
        assert rows[0]["units"] == "2.000"


class TestDashboardApi:
    def test_returns_every_section(self, admin_client_api: APIClient, paid_order: Any) -> None:
        response = admin_client_api.get("/api/v1/admin/dashboard/")

        assert response.status_code == 200
        assert set(response.data) >= {
            "period",
            "revenue",
            "orders",
            "counters",
            "charts",
            "customers",
            "recent_orders",
            "alerts",
        }
        assert response.data["revenue"]["period"] == "25.00"

    def test_chart_series_are_precomputed(
        self, admin_client_api: APIClient, paid_order: Any
    ) -> None:
        charts = admin_client_api.get("/api/v1/admin/dashboard/").data["charts"]
        assert isinstance(charts["revenue_by_day"], list)
        assert isinstance(charts["top_products"], list)

    def test_comparison_is_null_without_a_baseline(
        self, admin_client_api: APIClient, paid_order: Any
    ) -> None:
        """ "No data to compare" must not be reported as "no change"."""
        assert (
            admin_client_api.get("/api/v1/admin/dashboard/").data["revenue"]["change_percentage"]
            is None
        )


class TestFinancialStatement:
    def test_projection_records_revenue_and_cogs(self, tenant: Any, paid_order: Any) -> None:
        from apps.finance.models import FinancialTransaction
        from apps.finance.services import project_order_to_ledger

        entries = project_order_to_ledger(paid_order)
        assert len(entries) == 2  # sales + COGS (pickup has no delivery income)

        codes = set(
            FinancialTransaction.objects.filter(tenant=tenant).values_list(
                "category__code", flat=True
            )
        )
        assert {"sales", "cogs"} <= codes

    def test_projection_is_idempotent(self, tenant: Any, paid_order: Any) -> None:
        from apps.finance.models import FinancialTransaction
        from apps.finance.services import project_order_to_ledger

        project_order_to_ledger(paid_order)
        project_order_to_ledger(paid_order)

        assert FinancialTransaction.objects.filter(tenant=tenant).count() == 2

    def test_statement_separates_gross_profit_from_net_result(
        self, tenant: Any, paid_order: Any
    ) -> None:
        from apps.finance.services import profit_and_loss, project_order_to_ledger, record_expense

        project_order_to_ledger(paid_order)
        record_expense(
            tenant=tenant,
            category_code="rent",
            amount=Decimal("5.00"),
            occurred_on=date.today(),
            description="Aluguel",
        )

        statement = profit_and_loss(
            tenant_id=tenant.pk,
            start=date.today() - timedelta(days=1),
            end=date.today() + timedelta(days=1),
        )
        assert statement["revenue"] == "25.00"
        assert statement["cogs"] == "16.00"  # 2 × 8.00
        assert statement["gross_profit"] == "9.00"
        assert statement["net_result"] == "4.00"
        assert statement["expenses_recorded"] is True

    def test_statement_flags_missing_expenses(self, tenant: Any, paid_order: Any) -> None:
        from apps.finance.services import profit_and_loss, project_order_to_ledger

        project_order_to_ledger(paid_order)
        statement = profit_and_loss(
            tenant_id=tenant.pk,
            start=date.today() - timedelta(days=1),
            end=date.today() + timedelta(days=1),
        )
        assert statement["expenses_recorded"] is False

    def test_ledger_entries_are_voided_not_deleted(self, tenant: Any) -> None:
        """Invariant #9."""
        from apps.finance.models import FinancialTransaction, TransactionStatus
        from apps.finance.services import record_expense, soft_delete_transaction

        entry = record_expense(
            tenant=tenant,
            category_code="rent",
            amount=Decimal("100.00"),
            occurred_on=date.today(),
            description="Aluguel",
        )
        soft_delete_transaction(entry)
        entry.refresh_from_db()

        assert entry.deleted_at is not None
        assert entry.status == TransactionStatus.CANCELLED
        assert FinancialTransaction.objects.filter(pk=entry.pk).exists()


class TestPdfGeneration:
    def test_receipt_is_a_pdf(self, paid_order: Any) -> None:
        from apps.reports.pdf import render_order_receipt

        content = render_order_receipt(paid_order)
        assert content.startswith(b"%PDF-")
        assert len(content) > 800

    def test_receipt_is_stored_once(self, paid_order: Any) -> None:
        from apps.media.models import Document
        from apps.reports.services import generate_order_receipt

        first = generate_order_receipt(paid_order)
        second = generate_order_receipt(paid_order)

        assert first.pk == second.pk
        assert Document.objects.filter(related_type="order_receipt").count() == 1

    def test_receipt_endpoint(self, customer_client: APIClient, paid_order: Any) -> None:
        response = customer_client.get(f"/api/v1/orders/{paid_order.number}/receipt/")

        assert response.status_code == 200
        assert response.data["download_url"]

    def test_sales_report_pdf(self, tenant: Any, paid_order: Any) -> None:
        from apps.reports.pdf import render_sales_report
        from apps.reports.services import sales_report

        period = named_period("last_30", tenant=tenant)
        data = sales_report(tenant=tenant, period=period)
        content = render_sales_report(
            tenant=tenant,
            period_label="Teste",
            summary=data["summary"],
            daily=data["daily"],
            products=data["products"],
        )
        assert content.startswith(b"%PDF-")

    def test_export_returns_a_job(self, admin_client_api: APIClient, paid_order: Any) -> None:
        response = admin_client_api.post(
            "/api/v1/admin/reports/export/", {"report_type": "SALES"}, format="json"
        )
        assert response.status_code == 202
        # CELERY_TASK_ALWAYS_EAGER runs it inline in tests.
        assert response.data["id"]

    def test_report_job_completes(self, tenant: Any, admin_user: Any, paid_order: Any) -> None:
        from apps.reports.models import ReportJob, ReportStatus
        from apps.reports.services import run_report_job

        period = named_period("last_30", tenant=tenant)
        job = ReportJob.objects.create(
            tenant=tenant,
            report_type="SALES",
            parameters={
                "period": period.key,
                "start": period.start_date.isoformat(),
                "end": period.end_date.isoformat(),
            },
            requested_by=admin_user,
        )
        run_report_job(job)
        job.refresh_from_db()

        assert job.status == ReportStatus.COMPLETED
        assert job.asset is not None
