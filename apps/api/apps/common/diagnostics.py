"""
System diagnostics.

Answers one question — *is anything wrong right now, and where?* — for an
operator who is looking at a slow page or a customer complaint and needs to know
whether the platform or their own data is at fault.

Three rules shape what this module is allowed to report.

**Never a secret.** Every check reports derived facts: whether a client could
connect, how long it took, how many rows are in a state. A password, a token, a
bucket key or a connection string never appears in the payload, not even
partially masked — a masked secret still tells an attacker its length and shape.

**Never another tenant's data.** The counts are scoped by tenant. Infrastructure
checks (database, broker, storage) are inherently shared, so they report
*liveness only*: reachable, and how fast. "How many rows are in the orders
table" is a different question and is not asked here.

**Never block.** Every probe has a timeout and every failure is caught. A
diagnostics page that hangs because the thing it is diagnosing is down is worse
than no page: it removes the one screen that would have said so.
"""

from __future__ import annotations

import logging
import platform
import time
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import django
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger("murasfood.diagnostics")

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"
UNKNOWN = "unknown"

#: Ordered worst-last, so the overall status is `max()` over what was seen.
SEVERITY: dict[str, int] = {OK: 0, UNKNOWN: 1, DEGRADED: 2, DOWN: 3}

#: A probe slower than this is reported as degraded even when it succeeds. Set
#: well above normal local latency: the point is to catch a dying dependency,
#: not to flag a busy moment.
SLOW_MS = 1000.0

#: How long to wait on the broker before calling it unreachable.
#:
#: `ping` is a broadcast with no known audience, so it always costs the full
#: timeout — there is no reply count that lets it return early. That makes this
#: the floor on how long the diagnostics page takes, so it is kept short.
BROKER_TIMEOUT_SECONDS = 1.5


@dataclass
class Check:
    """One probe and what it found."""

    key: str
    label: str
    status: str = UNKNOWN
    detail: str = ""
    latency_ms: float | None = None
    #: Structured extras the UI can render as a small table. Must never carry
    #: credentials — see the module docstring.
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timed(probe: Any) -> tuple[Any, float]:
    """Run ``probe`` and report how long it took, in milliseconds."""
    started = time.perf_counter()
    result = probe()
    return result, round((time.perf_counter() - started) * 1000, 1)


def _grade(latency_ms: float, *, slow: float = SLOW_MS) -> str:
    """Succeeded, but was it healthy? Slow is a real failure mode."""
    return OK if latency_ms < slow else DEGRADED


# =============================================================================
# Infrastructure
# =============================================================================
def check_database() -> Check:
    """Round-trip a trivial query, and report whether migrations are current.

    Unapplied migrations are a *configuration* fault rather than an outage: the
    service answers, but not the way the code expects, and the symptom is
    usually a column that does not exist somewhere unrelated.
    """
    check = Check(key="database", label="PostgreSQL")
    try:

        def probe() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        _, latency = _timed(probe)
        check.latency_ms = latency
        check.status = _grade(latency)
        check.detail = f"{connection.vendor} responded in {latency} ms"
        check.meta["vendor"] = connection.vendor
    except Exception as error:
        check.status = DOWN
        check.detail = _safe_error(error)
        return check

    try:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        check.meta["pending_migrations"] = len(pending)
        if pending:
            check.status = DEGRADED
            check.detail = f"{len(pending)} migration(s) not applied"
    except Exception as error:
        check.meta["migrations"] = f"could not be read: {_safe_error(error)}"

    return check


def check_cache() -> Check:
    """Write and read one key. A cache that accepts writes it cannot serve is
    worse than one that is plainly down, so this checks the round trip."""
    check = Check(key="cache", label="Redis (cache)")
    token = f"diag-{timezone.now().timestamp()}"
    try:

        def probe() -> Any:
            cache.set("murasfood:diagnostics", token, timeout=10)
            return cache.get("murasfood:diagnostics")

        value, latency = _timed(probe)
        check.latency_ms = latency
        if value != token:
            check.status = DEGRADED
            check.detail = "The value written could not be read back"
        else:
            check.status = _grade(latency)
            check.detail = f"Round trip in {latency} ms"
    except Exception as error:
        check.status = DOWN
        check.detail = _safe_error(error)
    return check


def check_broker() -> Check:
    """Ask Celery which workers answer.

    ``ping`` is a broadcast with a timeout, so an unreachable broker costs the
    timeout rather than hanging. No workers is *degraded*, not down: the web
    tier still serves pages, but every queued email and report is stuck.
    """
    check = Check(key="workers", label="Celery workers")
    try:
        from config.celery import app as celery_app

        def probe() -> Any:
            return celery_app.control.ping(timeout=BROKER_TIMEOUT_SECONDS)

        replies, latency = _timed(probe)
        check.latency_ms = latency
        names = sorted(name for reply in (replies or []) for name in reply)
        check.meta["workers"] = names

        if not names:
            check.status = DEGRADED
            check.detail = "No worker answered — queued work will not run"
        else:
            check.status = OK
            check.detail = f"{len(names)} worker(s) responding"
    except Exception as error:
        check.status = DOWN
        check.detail = _safe_error(error)
    return check


def check_queue_depth() -> Check:
    """How much work is waiting.

    Read straight from the broker's list rather than through Celery, because
    ``inspect`` talks to workers and a backlog is most interesting precisely
    when no worker is answering.
    """
    check = Check(key="queue", label="Queue backlog")
    try:
        import redis

        def probe() -> int:
            client = redis.Redis.from_url(
                settings.CELERY_BROKER_URL,
                socket_connect_timeout=BROKER_TIMEOUT_SECONDS,
                socket_timeout=BROKER_TIMEOUT_SECONDS,
            )
            return int(client.llen("celery"))

        depth, latency = _timed(probe)
        check.latency_ms = latency
        check.meta["pending_tasks"] = depth
        # A queue is meant to have things in it. Only a backlog that is not
        # draining is a problem, and the threshold here is "a human would
        # notice", not "non-zero".
        check.status = OK if depth < 100 else DEGRADED
        check.detail = f"{depth} task(s) waiting"
    except Exception as error:
        check.status = UNKNOWN
        check.detail = _safe_error(error)
    return check


def check_storage() -> Check:
    """Confirm the object store answers for the bucket we actually use."""
    check = Check(key="storage", label="Object storage")
    try:
        from apps.media.storage import S3CompatibleStorage, get_storage

        backend = get_storage()
        check.meta["backend"] = type(backend).__name__

        if not isinstance(backend, S3CompatibleStorage):
            check.status = OK
            check.detail = "Local filesystem storage"
            return check

        def probe() -> None:
            backend._client.head_bucket(Bucket=backend.bucket)

        _, latency = _timed(probe)
        check.latency_ms = latency
        check.status = _grade(latency)
        check.detail = f"Bucket reachable in {latency} ms"
        # The bucket *name* is configuration, not a credential, and an operator
        # needs it to know which environment they are looking at.
        check.meta["bucket"] = backend.bucket
    except Exception as error:
        check.status = DOWN
        check.detail = _safe_error(error)
    return check


def check_email(tenant_id: Any) -> Check:
    """Whether mail is configured and whether it is actually going out.

    A configured backend that fails on every send looks identical to a working
    one from the outside, so this reports the last day's delivery outcomes
    rather than the settings.
    """
    check = Check(key="email", label="Transactional email")
    try:
        from apps.notifications.models import EmailLog, EmailStatus

        since = timezone.now() - timedelta(hours=24)
        rows = EmailLog.objects.filter(tenant_id=tenant_id, created_at__gte=since)

        sent = rows.filter(status=EmailStatus.SENT).count()
        failed = rows.filter(status=EmailStatus.FAILED).count()
        queued = rows.filter(status=EmailStatus.QUEUED).count()

        check.meta = {"sent_24h": sent, "failed_24h": failed, "queued": queued}
        check.meta["backend"] = settings.EMAIL_BACKEND.rsplit(".", 1)[-1]

        if failed and failed >= sent:
            check.status = DOWN
            check.detail = f"{failed} of the last {failed + sent} messages failed"
        elif failed or queued > 50:
            check.status = DEGRADED
            check.detail = f"{failed} failed, {queued} still queued"
        else:
            check.status = OK
            check.detail = f"{sent} delivered in the last 24 h"
    except Exception as error:
        check.status = UNKNOWN
        check.detail = _safe_error(error)
    return check


def check_scheduler(tenant_id: Any) -> Check:
    """Is the beat scheduler alive?

    Inferred from the work it causes rather than from beat itself: reservations
    expire on a timer, so a reservation that is long past its expiry and still
    held means nothing has swept it.
    """
    check = Check(key="scheduler", label="Scheduled jobs")
    try:
        from apps.inventory.models import ReservationStatus, StockReservation

        stale = StockReservation.objects.filter(
            tenant_id=tenant_id,
            status=ReservationStatus.HELD,
            expires_at__lt=timezone.now() - timedelta(minutes=30),
        ).count()

        check.meta = {"overdue_reservations": stale, "jobs": len(settings.CELERY_BEAT_SCHEDULE)}
        if stale:
            check.status = DEGRADED
            check.detail = f"{stale} reservation(s) past expiry and not swept"
        else:
            check.status = OK
            check.detail = f"{len(settings.CELERY_BEAT_SCHEDULE)} periodic job(s) registered"
    except Exception as error:
        check.status = UNKNOWN
        check.detail = _safe_error(error)
    return check


# =============================================================================
# Application state
# =============================================================================
def check_configuration() -> Check:
    """Settings that are wrong in a way no exception will ever report.

    `DEBUG` in production leaks tracebacks with local variables in them, and a
    short `SECRET_KEY` weakens every signature the platform issues. Neither
    breaks anything visibly, which is exactly why they belong on this page.
    """
    check = Check(key="configuration", label="Configuration")
    warnings: list[str] = []

    if settings.DEBUG:
        warnings.append("DEBUG is on")
    if len(getattr(settings, "SECRET_KEY", "")) < 50:
        warnings.append("SECRET_KEY is shorter than 50 characters")
    if not settings.DEBUG and "*" in getattr(settings, "ALLOWED_HOSTS", []):
        warnings.append("ALLOWED_HOSTS accepts any host")
    if not settings.DEBUG and not getattr(settings, "SECURE_SSL_REDIRECT", False):
        warnings.append("SECURE_SSL_REDIRECT is off")

    check.meta = {
        "debug": settings.DEBUG,
        # Booleans only. Whether a key exists is operational information;
        # the key itself is not.
        "secret_key_set": bool(getattr(settings, "SECRET_KEY", "")),
        "allowed_hosts": len(getattr(settings, "ALLOWED_HOSTS", [])),
        "warnings": warnings,
    }
    check.status = DEGRADED if warnings else OK
    check.detail = "; ".join(warnings) if warnings else "No configuration warnings"
    return check


def _safe_error(error: Exception) -> str:
    """A message an operator can act on, with nothing sensitive in it.

    Driver exceptions happily include the DSN they failed to connect with, and
    a DSN carries a password. The type plus a truncated message is enough to
    tell a refused connection from a bad credential without printing either.
    """
    text = str(error).split("\n")[0][:160]
    for marker in ("://", "password", "secret", "token", "key="):
        if marker in text.lower():
            return type(error).__name__
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


# =============================================================================
# Report
# =============================================================================
def application_info() -> dict[str, Any]:
    """What is running, so a bug report can name it."""
    return {
        "environment": getattr(settings, "ENVIRONMENT", "unknown"),
        "debug": settings.DEBUG,
        "python": platform.python_version(),
        "django": django.get_version(),
        "time_zone": settings.TIME_ZONE,
        "server_time": timezone.now().isoformat(),
    }


def tenant_snapshot(tenant_id: Any) -> dict[str, Any]:
    """The merchant's own numbers, for the same moment as the checks above."""
    from django.db.models import F

    from apps.catalog.models import Product
    from apps.inventory.models import InventoryItem
    from apps.orders.models import Order

    today = timezone.now().date()
    snapshot: dict[str, Any] = {}

    try:
        snapshot["orders_today"] = Order.objects.filter(
            tenant_id=tenant_id, created_at__date=today
        ).count()
        snapshot["products"] = Product.objects.filter(tenant_id=tenant_id).count()

        # Counted in SQL. `is_out_of_stock` is a Python property, so evaluating
        # it per row would load the whole inventory table into memory to produce
        # a single integer — fine for a demo shop, ruinous for a real one.
        snapshot["out_of_stock"] = (
            InventoryItem.objects.filter(tenant_id=tenant_id, track_stock=True)
            .filter(quantity__lte=F("reserved_quantity"))
            .count()
        )
    except Exception as error:
        snapshot["error"] = _safe_error(error)

    return snapshot


def run_diagnostics(*, tenant_id: Any) -> dict[str, Any]:
    """Every check, plus an overall verdict.

    The verdict is the worst individual result. Averaging would let one dead
    dependency hide behind five healthy ones, which is the opposite of what this
    page is for.
    """
    checks = [
        check_database(),
        check_cache(),
        check_broker(),
        check_queue_depth(),
        check_storage(),
        check_email(tenant_id),
        check_scheduler(tenant_id),
        check_configuration(),
    ]

    overall = max((check.status for check in checks), key=lambda status: SEVERITY[status])

    return {
        "status": overall,
        "generated_at": timezone.now().isoformat(),
        "application": application_info(),
        "checks": [check.as_dict() for check in checks],
        "tenant": tenant_snapshot(tenant_id),
    }
