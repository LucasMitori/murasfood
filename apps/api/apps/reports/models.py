"""
Report job models.

Large reports are produced asynchronously (spec §28): a merchant asking for a
year of sales must not hold an HTTP worker open while PostgreSQL aggregates and
ReportLab renders. The job row is what the frontend polls.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class ReportType(models.TextChoices):
    SALES = "SALES", _("Sales report")
    PRODUCTS = "PRODUCTS", _("Product performance")
    CUSTOMERS = "CUSTOMERS", _("Customer report")
    INVENTORY = "INVENTORY", _("Inventory report")
    FINANCIAL = "FINANCIAL", _("Financial statement")
    ORDER_RECEIPT = "ORDER_RECEIPT", _("Order receipt")


class ReportFormat(models.TextChoices):
    PDF = "PDF", _("PDF")
    CSV = "CSV", _("CSV")


class ReportStatus(models.TextChoices):
    QUEUED = "QUEUED", _("Queued")
    RUNNING = "RUNNING", _("Running")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")


class ReportJob(TenantOwnedModel):
    """One requested export."""

    report_type = models.CharField(_("type"), max_length=20, choices=ReportType.choices)
    output_format = models.CharField(
        _("format"), max_length=6, choices=ReportFormat.choices, default=ReportFormat.PDF
    )
    status = models.CharField(
        _("status"), max_length=10, choices=ReportStatus.choices, default=ReportStatus.QUEUED
    )

    parameters = models.JSONField(
        _("parameters"),
        default=dict,
        blank=True,
        help_text=_("Period and filters the report was generated with."),
    )
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_jobs",
        verbose_name=_("generated file"),
    )
    error_message = models.CharField(_("error"), max_length=500, blank=True)

    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("report job")
        verbose_name_plural = _("report jobs")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status", "-created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.report_type} ({self.status})"

    @property
    def is_ready(self) -> bool:
        return self.status == ReportStatus.COMPLETED and self.asset_id is not None
