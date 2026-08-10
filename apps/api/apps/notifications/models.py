"""
Notification models.

Email templates are rows, not files, so a merchant can reword "your order is
ready" without a deploy (spec §25). Templates interpolate a fixed set of
variables and can never execute code — a merchant-editable template that
evaluates arbitrary expressions is a server-side template injection waiting to
happen.

``EmailLog`` exists because "did the customer get the email?" is a question
support will ask, and the answer must not be "check the SMTP server".
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class NotificationChannel(models.TextChoices):
    EMAIL = "EMAIL", _("Email")
    PUSH = "PUSH", _("Push notification")
    SMS = "SMS", _("SMS")
    IN_APP = "IN_APP", _("In-app")


class NotificationStatus(models.TextChoices):
    QUEUED = "QUEUED", _("Queued")
    SENT = "SENT", _("Sent")
    FAILED = "FAILED", _("Failed")
    READ = "READ", _("Read")


class EmailStatus(models.TextChoices):
    QUEUED = "QUEUED", _("Queued")
    SENT = "SENT", _("Sent")
    FAILED = "FAILED", _("Failed")
    RETRYING = "RETRYING", _("Retrying")


class EmailTemplate(TenantOwnedModel):
    """A merchant-editable transactional email."""

    key = models.CharField(
        _("key"),
        max_length=64,
        help_text=_("Stable identifier used by the code, e.g. order.payment_confirmed."),
    )
    locale = models.CharField(_("locale"), max_length=10, default="pt-BR")
    subject = models.CharField(_("subject"), max_length=255)
    html_body = models.TextField(_("HTML body"))
    text_body = models.TextField(
        _("plain text body"),
        blank=True,
        help_text=_("Fallback for clients that do not render HTML."),
    )
    available_variables = models.JSONField(
        _("available variables"),
        default=list,
        blank=True,
        help_text=_("Documents which placeholders this template accepts."),
    )
    version = models.PositiveIntegerField(_("version"), default=1)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("email template")
        verbose_name_plural = _("email templates")
        ordering = ["key", "locale"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key", "locale"], name="uniq_email_template_tenant_key_locale"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key} [{self.locale}]"


class EmailLog(TenantOwnedModel):
    """One attempted delivery."""

    template_key = models.CharField(_("template"), max_length=64, db_index=True)
    recipient = models.EmailField(_("recipient"))
    subject = models.CharField(_("subject"), max_length=255)

    status = models.CharField(
        _("status"), max_length=12, choices=EmailStatus.choices, default=EmailStatus.QUEUED
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    last_error = models.CharField(_("last error"), max_length=500, blank=True)
    provider_message_id = models.CharField(_("provider message id"), max_length=255, blank=True)

    related_type = models.CharField(_("related type"), max_length=32, blank=True)
    related_id = models.CharField(_("related id"), max_length=64, blank=True, db_index=True)

    idempotency_key = models.CharField(
        _("idempotency key"),
        max_length=128,
        blank=True,
        db_index=True,
        help_text=_("Prevents sending the same notification twice."),
    )

    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)

    class Meta:
        verbose_name = _("email log")
        verbose_name_plural = _("email logs")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_email_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["related_type", "related_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.template_key} → {self.recipient} ({self.status})"


class Notification(TenantOwnedModel):
    """A message shown to a customer in the app or sent over another channel."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(
        _("channel"),
        max_length=12,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
    )
    notification_type = models.CharField(_("type"), max_length=48, db_index=True)
    title = models.CharField(_("title"), max_length=160)
    body = models.CharField(_("body"), max_length=500, blank=True)
    payload = models.JSONField(
        _("payload"),
        default=dict,
        blank=True,
        help_text=_("Deep-link data, e.g. the order the notification refers to."),
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=NotificationStatus.choices,
        default=NotificationStatus.QUEUED,
    )
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.title
