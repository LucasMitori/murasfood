"""Read-side queries for tenants."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Prefetch
from django.utils import timezone

from .models import BusinessHours, Tenant

if TYPE_CHECKING:  # pragma: no cover
    from django.db.models import QuerySet


def tenant_with_configuration(tenant_id: object) -> Tenant | None:
    """Fetch a tenant with branding, settings and hours in a single round trip."""
    return (
        Tenant.objects.filter(pk=tenant_id)
        .select_related("branding", "settings")
        .prefetch_related(
            Prefetch(
                "business_hours", queryset=BusinessHours.objects.order_by("weekday", "opens_at")
            )
        )
        .first()
    )


def tenant_timezone(tenant: Tenant) -> ZoneInfo:
    """Return the tenant's timezone, falling back to UTC when misconfigured.

    Reports must never be computed in the server's timezone: a 23:30 sale in
    São Paulo belongs to that local business day, not to the following UTC day
    (spec §86).
    """
    try:
        return ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def tenant_local_now(tenant: Tenant) -> datetime:
    """Current time in the tenant's timezone."""
    return timezone.now().astimezone(tenant_timezone(tenant))


def business_hours_for(tenant: Tenant, weekday: int) -> QuerySet[BusinessHours]:
    """Opening windows for an ISO weekday (Monday = 1)."""
    return tenant.business_hours.filter(weekday=weekday, is_closed=False).order_by("opens_at")


def is_open_at(tenant: Tenant, moment: datetime | None = None) -> bool:
    """Whether the store is open at ``moment`` (defaults to now, tenant-local).

    A tenant with no configured hours is treated as always open: an incomplete
    setup should not silently stop a merchant from selling.
    """
    local = (moment or timezone.now()).astimezone(tenant_timezone(tenant))
    windows = list(business_hours_for(tenant, local.isoweekday()))
    if not windows:
        return not tenant.business_hours.exists()

    current: time = local.time()
    return any(window.opens_at <= current <= window.closes_at for window in windows)
