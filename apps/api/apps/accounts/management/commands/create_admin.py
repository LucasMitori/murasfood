"""
Create (or repair) the platform administrator.

Idempotent: running it again updates the existing account rather than failing,
which makes it safe to call on every deploy and after a database restore.

The account is a tenant ``ADMINISTRATOR``, which holds every permission code in
the catalogue by definition (see ``User.permission_codes``), *and* is granted
the administrator role explicitly so the assignment is visible in the admin UI
rather than only implied by the user type.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

DEFAULT_EMAIL = "devmitori@gmail.com"
DEFAULT_NAME = "Admin"
DEFAULT_PASSWORD = "Admin@Market2026"  # noqa: S105 - development credential, overridable


class Command(BaseCommand):
    help = "Create or update the administrator account with every permission."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--name", default=DEFAULT_NAME)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument(
            "--tenant",
            default="",
            help="Tenant slug. Defaults to the only tenant when there is exactly one.",
        )
        parser.add_argument(
            "--only-user",
            action="store_true",
            help="Remove every other account in the tenant, leaving just this one.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        from apps.accounts.constants import SystemRole, UserType
        from apps.accounts.models import Role, User
        from apps.accounts.services import assign_role, ensure_system_roles
        from apps.tenants.bootstrap import bootstrap_tenant
        from apps.tenants.models import Tenant
        from apps.tenants.services import create_tenant

        tenant = self._resolve_tenant(Tenant, options["tenant"])
        if tenant is None:
            tenant = create_tenant(
                legal_name="MurasFood Demonstração LTDA",
                trade_name="MurasFood",
                support_email=options["email"],
                slug="demo",
                city="São Paulo",
                state="SP",
            )
            self.stdout.write(self.style.SUCCESS(f"Created tenant '{tenant.slug}'."))

        # Guarantees roles, permissions, units, delivery config and email
        # templates exist before anything is assigned to them.
        bootstrap_tenant(tenant)
        ensure_system_roles(tenant)

        email = options["email"].strip().lower()
        name_parts = options["name"].strip().split(" ", 1)

        user = User.objects.filter(tenant=tenant, email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                password=options["password"],
                tenant=tenant,
                first_name=name_parts[0],
                last_name=name_parts[1] if len(name_parts) > 1 else "",
                user_type=UserType.ADMINISTRATOR,
                is_verified=True,
                is_staff=True,
            )
            created = True
        else:
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ""
            user.user_type = UserType.ADMINISTRATOR
            user.is_verified = True
            user.is_active = True
            user.is_staff = True
            user.set_password(options["password"])
            user.save()
            created = False

        user.verified_at = user.verified_at or timezone.now()
        user.save(update_fields=["verified_at", "updated_at"])

        # Assign every role the tenant has, not just the administrator one, so
        # the account can exercise any screen gated on a specific role.
        for role in Role.objects.filter(tenant=tenant):
            assign_role(user, role, granted_by=user)
        user.refresh_permission_cache()

        if options["only_user"]:
            removed, _ = User.objects.filter(tenant=tenant).exclude(pk=user.pk).delete()
            if removed:
                self.stdout.write(self.style.WARNING(f"Removed {removed} other account(s)."))

        administrator_role = Role.objects.filter(
            tenant=tenant, slug=SystemRole.ADMINISTRATOR
        ).first()

        self.stdout.write(self.style.SUCCESS("\nAdministrator ready.\n"))
        self.stdout.write(f"  Tenant      : {tenant.trade_name} ({tenant.slug})")
        self.stdout.write(f"  Email       : {user.email}")
        self.stdout.write(f"  Password    : {options['password']}")
        self.stdout.write(f"  Type        : {user.user_type}")
        self.stdout.write(f"  Roles       : {', '.join(sorted(r.slug for r in user.roles.all()))}")
        self.stdout.write(f"  Permissions : {len(user.permission_codes())} codes")
        self.stdout.write(
            f"  Role record : {administrator_role.name if administrator_role else 'missing'}"
        )
        self.stdout.write(
            self.style.SUCCESS(f"\n  {'Created' if created else 'Updated'} successfully.\n")
        )

    @staticmethod
    def _resolve_tenant(tenant_model: Any, slug: str) -> Any:
        if slug:
            return tenant_model.objects.filter(slug=slug).first()

        # With exactly one tenant the choice is unambiguous; with several,
        # guessing would be how an admin lands in the wrong merchant.
        tenants = list(tenant_model.objects.all()[:2])
        if len(tenants) == 1:
            return tenants[0]
        if len(tenants) > 1:
            raise SystemExit(
                "Several tenants exist. Pass --tenant <slug> to choose one."
            )
        return None
