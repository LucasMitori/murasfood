"""
A report comes back in the format that was asked for.

`output_format` was a field on the model, a choice in the API and a parameter
the client could send — and `run_report_job` never read it. Every job rendered
a PDF and filed it under a `.pdf` name, so a merchant who chose CSV got a PDF
and no error to explain why their spreadsheet would not open it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from apps.reports.models import ReportFormat, ReportJob, ReportStatus, ReportType
from apps.reports.periods import build_period
from apps.reports.services import run_report_job

pytestmark = pytest.mark.django_db


def job_for(tenant: Any, *, report_type: str, fmt: str) -> ReportJob:
    from apps.tenants.selectors import tenant_timezone

    period = build_period(
        key="custom",
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
        tzinfo=tenant_timezone(tenant),
    )
    return ReportJob.objects.create(
        tenant=tenant,
        report_type=report_type,
        output_format=fmt,
        parameters={
            "period": period.key,
            "start": period.start_date.isoformat(),
            "end": period.end_date.isoformat(),
        },
    )


class TestFormatIsHonoured:
    @pytest.mark.parametrize("report_type", [ReportType.SALES, ReportType.FINANCIAL])
    def test_csv_produces_a_csv(self, tenant: Any, report_type: str) -> None:
        job = run_report_job(job_for(tenant, report_type=report_type, fmt=ReportFormat.CSV))

        assert job.status == ReportStatus.COMPLETED, job.error_message
        assert job.asset is not None
        assert job.asset.original_filename.endswith(".csv")
        assert "csv" in job.asset.content_type

    @pytest.mark.parametrize("report_type", [ReportType.SALES, ReportType.FINANCIAL])
    def test_pdf_still_produces_a_pdf(self, tenant: Any, report_type: str) -> None:
        """The default path, which is what everything used to do regardless."""
        job = run_report_job(job_for(tenant, report_type=report_type, fmt=ReportFormat.PDF))

        assert job.status == ReportStatus.COMPLETED, job.error_message
        assert job.asset.original_filename.endswith(".pdf")
        assert job.asset.content_type == "application/pdf"

    def test_the_csv_carries_headings(self, tenant: Any) -> None:
        """A spreadsheet without a header row is a wall of numbers."""
        from apps.media.storage import get_storage

        job = run_report_job(
            job_for(tenant, report_type=ReportType.FINANCIAL, fmt=ReportFormat.CSV)
        )
        with get_storage().open(job.asset.storage_key) as handle:
            content = handle.read().decode("utf-8-sig")

        assert content.splitlines()[0] == "Item;Valor"
        assert "Receita" in content
