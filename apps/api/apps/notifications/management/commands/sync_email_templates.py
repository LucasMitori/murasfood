"""
Install any default email template a tenant is missing.

Templates are seeded when a tenant is created, so a template added to
``DEFAULT_TEMPLATES`` afterwards exists for nobody. The failure is quiet by
design — `queue_transactional_email` logs a warning and returns ``None`` rather
than breaking the operation that triggered it — which means a whole notification
can be dead in production with nothing but a log line to show for it.

Found exactly that way: the back-in-stock notice was written, wired and tested,
and sent nothing at all because the template row did not exist for the one shop
in the database.

Idempotent. Run on every deploy, beside `sync_roles`.

A template a merchant has edited is never touched: `get_or_create` matches on
(tenant, key, locale), so an existing row keeps whatever wording the shop gave
it.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.notifications.services import seed_default_templates
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Seed missing default email templates for every tenant."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", help="Slug of a single tenant.")
        parser.add_argument("--locale", help="Override the tenant's own locale.")

    def handle(self, *args: Any, **options: Any) -> None:
        tenants = Tenant.objects.all().order_by("slug")
        if options.get("tenant"):
            tenants = tenants.filter(slug=options["tenant"])
            if not tenants.exists():
                self.stderr.write(self.style.ERROR(f"No tenant {options['tenant']!r}."))
                return

        total = 0
        for tenant in tenants:
            created = seed_default_templates(tenant, locale=options.get("locale"))
            total += created
            self.stdout.write(f"  {tenant.slug}: {created} template(s) added")

        self.stdout.write(
            self.style.SUCCESS(f"{total} template(s) added across {tenants.count()} tenant(s).")
        )
