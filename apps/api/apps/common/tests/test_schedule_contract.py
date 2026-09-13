"""
The periodic jobs the system depends on must actually be scheduled.

Seven background jobs were written, documented as running "on a schedule", and
never added to `CELERY_BEAT_SCHEDULE`. Nothing failed — a task nobody calls
simply never runs, and its absence looks exactly like a quiet system:

  * a lost payment webhook left a paid order unfulfilled forever, with the
    polling backstop sitting there unused,
  * revenue never reached the finance ledger, whose projection ran only from
    the demo seeder,
  * low-stock alerts were never sent to anyone,
  * three cleanup jobs never ran, so their tables and buckets only grew.

The tests below check the two halves that can drift apart: a schedule naming a
task that does not exist, and a task that must run but is not named.
"""

from __future__ import annotations

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def _registered_task_names() -> set[str]:
    from config.celery import app

    app.loader.import_default_modules()
    return set(app.tasks.keys())


class TestScheduleIsCoherent:
    def test_every_scheduled_task_exists(self) -> None:
        """A renamed or deleted task leaves beat firing into the void.

        Beat logs the failure and carries on, so the only symptom is that the
        job silently stops happening.
        """
        registered = _registered_task_names()
        missing = [
            f"{name} -> {entry['task']}"
            for name, entry in settings.CELERY_BEAT_SCHEDULE.items()
            if entry["task"] not in registered
        ]

        assert missing == [], f"Scheduled tasks that do not exist: {missing}"

    def test_the_jobs_the_system_relies_on_are_scheduled(self) -> None:
        """Named individually, because each absence was its own outage.

        This is a list rather than a rule because "should this run
        periodically?" is a judgement about the job, not something derivable
        from its signature. `generate_report` takes an argument and is
        triggered by a user; these do not and are not.
        """
        required = {
            # A paid order that no webhook confirmed.
            "apps.payments.tasks.reconcile_pending_payments",
            # The only path from a paid order to the finance ledger.
            "apps.reports.tasks.project_paid_orders_to_ledger",
            # An order whose payment row was never created.
            "apps.orders.tasks.expire_unpaid_orders",
            # Restocking advice.
            "apps.inventory.tasks.notify_low_stock_all_tenants",
            # Stock held by an abandoned checkout.
            "apps.inventory.tasks.release_expired_reservations",
            # The PIX window closing.
            "apps.payments.tasks.expire_stale_payments",
            # Unbounded growth.
            "apps.media.tasks.cleanup_orphaned_assets",
            "apps.reports.tasks.cleanup_old_report_jobs",
            "apps.notifications.tasks.cleanup_old_notifications",
        }
        scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        assert required - scheduled == set(), f"Not scheduled: {sorted(required - scheduled)}"

    def test_expiry_runs_after_the_payment_window_not_during_it(self) -> None:
        """The order backstop must never race the payments layer.

        `expire_unpaid_orders` cancels; the payments layer moves the same order
        to PAYMENT_FAILED. Whichever runs first wins, so the backstop's window
        has to sit comfortably outside the PIX one.
        """
        from apps.orders.tasks import expire_unpaid_orders

        window_minutes = expire_unpaid_orders.__wrapped__.__defaults__[0]
        reservation_minutes = settings.STOCK_RESERVATION_TTL_SECONDS / 60

        assert window_minutes > reservation_minutes
