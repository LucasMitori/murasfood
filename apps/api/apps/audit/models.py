"""
Audit log.

Every sensitive action — price change, refund, permission grant, tenant
configuration edit — leaves a row here (spec §40). Rows are written once and
never updated: an audit trail you can edit is not an audit trail.

What is deliberately *not* stored: passwords, tokens, secrets, card data. The
writer redacts before persisting.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class AuditAction(models.TextChoices):
    """Well-known action names.

    Free-form strings are accepted too — the choices exist for filtering and
    documentation, not to constrain callers.
    """

    LOGIN = "account.login", _("Sign in")
    LOGOUT = "account.logout", _("Sign out")
    PASSWORD_CHANGED = "account.password_changed", _("Password changed")
    PERMISSION_CHANGED = "user.permissions_changed", _("Permissions changed")
    PRICE_CHANGED = "pricing.price_changed", _("Price changed")
    STOCK_ADJUSTED = "inventory.adjusted", _("Stock adjusted")
    ORDER_CANCELLED = "order.cancelled", _("Order cancelled")
    ORDER_STATUS_CHANGED = "order.status_changed", _("Order status changed")
    PAYMENT_STATUS_CHANGED = "payment.status_changed", _("Payment status changed")
    REFUND_ISSUED = "payment.refunded", _("Refund issued")
    TENANT_UPDATED = "tenant.updated", _("Store settings changed")
    DOCUMENT_DELETED = "document.deleted", _("Document deleted")


class AuditLog(BaseModel):
    """One recorded action."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
        verbose_name=_("tenant"),
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("actor"),
        help_text=_("Null for system-initiated actions such as webhooks."),
    )
    actor_label = models.CharField(
        _("actor label"),
        max_length=255,
        blank=True,
        help_text=_("Kept so the trail stays readable after an account is anonymised."),
    )

    action = models.CharField(_("action"), max_length=64, db_index=True)
    resource_type = models.CharField(_("resource type"), max_length=64, blank=True, db_index=True)
    resource_id = models.CharField(_("resource id"), max_length=64, blank=True, db_index=True)

    old_values = models.JSONField(_("previous values"), default=dict, blank=True)
    new_values = models.JSONField(_("new values"), default=dict, blank=True)

    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=255, blank=True)
    request_id = models.CharField(_("request id"), max_length=64, blank=True, db_index=True)

    class Meta:
        verbose_name = _("audit log")
        verbose_name_plural = _("audit logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "action", "-created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.action} by {self.actor_label or 'system'}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Block updates. Audit rows are immutable once written."""
        if self.pk and not self._state.adding:
            raise ValueError("Audit log entries cannot be modified.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]
