"""
Tenant provisioning.

Everything a merchant needs before they can sell: roles and permissions, units
of measure, delivery configuration, a chart of accounts and the default email
templates. Idempotent, so it doubles as a repair function for a tenant created
before a new default existed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

if TYPE_CHECKING:  # pragma: no cover
    from .models import Tenant

logger = logging.getLogger("murasfood.tenants")


@transaction.atomic
def bootstrap_tenant(tenant: Tenant) -> dict[str, Any]:
    """Provision a tenant with everything it needs to operate.

    Returns a summary of what was created, which the seed command reports.
    """
    from apps.accounts.services import ensure_system_roles
    from apps.catalog.services import ensure_default_units
    from apps.delivery.selectors import get_settings
    from apps.finance.services import ensure_chart_of_accounts
    from apps.notifications.services import seed_default_templates

    from .models import TenantBranding, TenantSettings

    TenantBranding.objects.get_or_create(tenant=tenant)
    TenantSettings.objects.get_or_create(tenant=tenant)

    roles = ensure_system_roles(tenant)
    units = ensure_default_units(tenant)
    get_settings(tenant)
    categories = ensure_chart_of_accounts(tenant)
    templates = seed_default_templates(tenant)

    summary = {
        "roles": len(roles),
        "units": len(units),
        "financial_categories": len(categories),
        "email_templates": templates,
    }
    logger.info(
        "tenant_bootstrapped",
        extra={"event": "tenants.bootstrapped", "tenant_id": str(tenant.pk), **summary},
    )
    return summary
