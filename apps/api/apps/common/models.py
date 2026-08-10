"""
Abstract base models.

Every persisted entity gets a UUID primary key and timestamps. Tenant-owned
entities additionally carry a ``tenant`` foreign key and a manager whose
:meth:`TenantQuerySet.for_tenant` is the *only* sanctioned way to read them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Self

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant


class UUIDModel(models.Model):
    """Primary key as a UUID.

    UUIDs keep identifiers non-guessable in URLs and let records be created
    offline or merged across databases without collisions (ADR-003).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """UUID primary key + timestamps. The default base for domain models."""

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    """QuerySet that makes tenant scoping explicit at every call site."""

    def for_tenant(self, tenant: Tenant | Any) -> Self:
        """Restrict to a single tenant.

        Accepts a ``Tenant`` instance or a raw id, so callers holding only
        ``request.tenant_id`` do not need an extra query.
        """
        tenant_id = getattr(tenant, "pk", tenant)
        if tenant_id is None:
            # Returning everything on a missing tenant would be a data leak.
            return self.none()
        return self.filter(tenant_id=tenant_id)

    def active(self) -> Self:
        """Rows flagged active, for models that have the field."""
        return self.filter(is_active=True)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Default manager for tenant-owned models."""


class TenantOwnedModel(BaseModel):
    """Base class for anything that belongs to exactly one merchant.

    ``on_delete=CASCADE`` is deliberate: removing a tenant must not leave
    orphaned catalog or order rows behind. Tenant deletion itself is guarded at
    the service layer and is never part of an ordinary admin flow.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name=_("tenant"),
        db_index=True,
    )

    objects = TenantManager()

    class Meta:
        abstract = True


class IdempotencyRecord(BaseModel):
    """One completed execution of an idempotent operation.

    See :mod:`apps.common.idempotency` for the surrounding protocol. Stored
    responses expire so keys can eventually be recycled and the table stays
    bounded.
    """

    key = models.CharField(_("key"), max_length=255)
    scope = models.CharField(_("scope"), max_length=64)
    tenant_id_value = models.UUIDField(_("tenant"), null=True, blank=True)
    user_id_value = models.UUIDField(_("user"), null=True, blank=True)
    request_hash = models.CharField(_("request hash"), max_length=64)
    response_status = models.PositiveSmallIntegerField(_("response status"), default=200)
    response_body = models.JSONField(_("response body"), default=dict, blank=True)
    expires_at = models.DateTimeField(_("expires at"), db_index=True)

    class Meta:
        verbose_name = _("idempotency record")
        verbose_name_plural = _("idempotency records")
        constraints = [
            # The same key may be reused across different operations and tenants,
            # but never twice within one scope for one tenant.
            models.UniqueConstraint(
                fields=["scope", "key", "tenant_id_value"],
                name="uniq_idempotency_scope_key_tenant",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.scope}:{self.key}"


class SoftDeleteQuerySet(TenantQuerySet):
    def alive(self) -> Self:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> Self:
        return self.filter(deleted_at__isnull=False)


class SoftDeleteModel(models.Model):
    """Marks a row as deleted instead of removing it.

    Used where history matters (financial records, audited documents). Invariant
    #9: financial transactions are never silently deleted.
    """

    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
