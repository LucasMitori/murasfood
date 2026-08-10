"""
Reporting periods.

Every window is resolved in the **tenant's** timezone (spec §86). A sale at
23:30 in São Paulo belongs to that day's takings even though the server stores
it as the next day in UTC — get this wrong and every daily figure a merchant
checks against their till will be off.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

#: Named windows offered by the dashboard's date filter.
PERIOD_CHOICES = (
    "today",
    "yesterday",
    "last_7",
    "last_30",
    "month",
    "previous_month",
    "year",
    "custom",
)


@dataclass(frozen=True)
class Period:
    """A resolved reporting window.

    ``start``/``end`` are timezone-aware datetimes for filtering timestamps;
    ``start_date``/``end_date`` are local dates for filtering ``DateField``
    columns such as the ledger's ``occurred_on``.
    """

    key: str
    start: datetime
    end: datetime
    start_date: date
    end_date: date
    tzinfo: Any

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def previous(self) -> Period:
        """The equally long window immediately before this one.

        Used for "vs. previous period" comparisons on the dashboard.
        """
        length = timedelta(days=self.days)
        new_end = self.start_date - timedelta(days=1)
        new_start = new_end - length + timedelta(days=1)
        return build_period(
            key=f"{self.key}_previous", start_date=new_start, end_date=new_end, tzinfo=self.tzinfo
        )


def build_period(*, key: str, start_date: date, end_date: date, tzinfo: Any) -> Period:
    """Wrap a local date range into a full :class:`Period`."""
    start = datetime.combine(start_date, time.min).replace(tzinfo=tzinfo)
    end = datetime.combine(end_date, time.max).replace(tzinfo=tzinfo)
    return Period(
        key=key, start=start, end=end, start_date=start_date, end_date=end_date, tzinfo=tzinfo
    )


def named_period(key: str, *, tenant: Tenant) -> Period:
    """Resolve one of the named windows for a tenant."""
    from apps.tenants.selectors import tenant_timezone

    tzinfo = tenant_timezone(tenant)
    today = timezone.now().astimezone(tzinfo).date()

    if key == "today":
        return build_period(key=key, start_date=today, end_date=today, tzinfo=tzinfo)
    if key == "yesterday":
        yesterday = today - timedelta(days=1)
        return build_period(key=key, start_date=yesterday, end_date=yesterday, tzinfo=tzinfo)
    if key == "last_7":
        return build_period(
            key=key, start_date=today - timedelta(days=6), end_date=today, tzinfo=tzinfo
        )
    if key == "month":
        return build_period(key=key, start_date=today.replace(day=1), end_date=today, tzinfo=tzinfo)
    if key == "previous_month":
        first_of_this_month = today.replace(day=1)
        last_of_previous = first_of_this_month - timedelta(days=1)
        return build_period(
            key=key,
            start_date=last_of_previous.replace(day=1),
            end_date=last_of_previous,
            tzinfo=tzinfo,
        )
    if key == "year":
        return build_period(
            key=key, start_date=today.replace(month=1, day=1), end_date=today, tzinfo=tzinfo
        )

    # Default: the last 30 days, the most useful window for a small merchant.
    return build_period(
        key="last_30", start_date=today - timedelta(days=29), end_date=today, tzinfo=tzinfo
    )


def resolve_period(request: Any, *, tenant: Tenant) -> Period:
    """Build a period from query parameters.

    ``?period=custom&start=2026-01-01&end=2026-01-31`` takes precedence; an
    unparsable date falls back to the named window rather than erroring, because
    a malformed URL should not break a dashboard.
    """
    from apps.tenants.selectors import tenant_timezone

    params = getattr(request, "query_params", {}) or {}
    key = str(params.get("period") or "last_30")

    raw_start = params.get("start")
    raw_end = params.get("end")
    if raw_start and raw_end:
        try:
            start_date = date.fromisoformat(str(raw_start))
            end_date = date.fromisoformat(str(raw_end))
        except ValueError:
            return named_period(key, tenant=tenant)

        if end_date < start_date:
            start_date, end_date = end_date, start_date
        # Cap the window: an unbounded range would scan the whole order table.
        if (end_date - start_date).days > 730:
            start_date = end_date - timedelta(days=730)

        return build_period(
            key="custom",
            start_date=start_date,
            end_date=end_date,
            tzinfo=tenant_timezone(tenant),
        )

    return named_period(key, tenant=tenant)


def month_bounds(reference: date) -> tuple[date, date]:
    """First and last day of ``reference``'s month."""
    _weekday, days_in_month = monthrange(reference.year, reference.month)
    return reference.replace(day=1), reference.replace(day=days_in_month)
