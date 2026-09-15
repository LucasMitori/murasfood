"""
Re-apply the permission catalogue to every tenant's system roles.

Adding a code to ``PERMISSION_CATALOGUE`` creates the row, but nothing grants
it: ``ensure_system_roles`` runs when a tenant is *created*, so an existing
merchant's administrator role keeps whatever set it was built with. The symptom
is a feature that works for a shop created after the deploy and 403s for every
shop created before it, which is a miserable thing to debug.

Idempotent, and safe to run on every deploy.

Merchant-authored roles are left alone. They are not ours to edit, and a
merchant who removed a permission on purpose should not find it back tomorrow.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.services import ensure_system_roles, sync_permissions
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Sync the permission catalogue and re-apply it to system roles."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--tenant",
            help="Slug of a single tenant. Omit to process every tenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        created = sync_permissions()
        self.stdout.write(f"Permissions: {created} new code(s) registered.")

        tenants = Tenant.objects.all().order_by("slug")
        if options.get("tenant"):
            tenants = tenants.filter(slug=options["tenant"])
            if not tenants.exists():
                self.stderr.write(self.style.ERROR(f"No tenant {options['tenant']!r}."))
                return

        if options.get("dry_run"):
            self.stdout.write(
                f"Would re-apply system roles for {tenants.count()} tenant(s). No changes written."
            )
            return

        for tenant in tenants:
            roles = ensure_system_roles(tenant)
            counts = ", ".join(
                f"{slug}={role.permissions.count()}" for slug, role in sorted(roles.items())
            )
            self.stdout.write(f"  {tenant.slug}: {counts}")

        self.stdout.write(self.style.SUCCESS(f"Synced {tenants.count()} tenant(s)."))
