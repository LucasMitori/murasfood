"""Tenant business operations."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.text import slugify

from .models import Tenant, TenantBranding, TenantSettings


@transaction.atomic
def create_tenant(
    *,
    legal_name: str,
    trade_name: str,
    support_email: str,
    slug: str | None = None,
    **extra: Any,
) -> Tenant:
    """Create a merchant with its branding and settings rows.

    Branding and settings are created eagerly so no code path has to handle a
    half-configured tenant, and so a merchant can be themed immediately after
    onboarding.
    """
    candidate = slugify(slug or trade_name)[:50].strip("-") or "store"
    unique_slug = candidate
    suffix = 2
    while Tenant.objects.filter(slug=unique_slug).exists():
        unique_slug = f"{candidate[:46]}-{suffix}"
        suffix += 1

    tenant = Tenant.objects.create(
        slug=unique_slug,
        legal_name=legal_name,
        trade_name=trade_name,
        support_email=support_email,
        **extra,
    )
    TenantBranding.objects.create(tenant=tenant)
    TenantSettings.objects.create(tenant=tenant)
    return tenant


def update_branding(tenant: Tenant, **fields: Any) -> TenantBranding:
    """Patch branding, creating the row when a legacy tenant lacks one."""
    branding, _ = TenantBranding.objects.get_or_create(tenant=tenant)

    # Media ids arrive as `<field>_id` from the serializer.
    for key in ("logo_id", "logo_dark_id", "favicon_id"):
        if key in fields:
            setattr(branding, key, fields.pop(key))

    for key, value in fields.items():
        setattr(branding, key, value)
    branding.save()
    return branding


def update_settings(tenant: Tenant, **fields: Any) -> TenantSettings:
    """Patch operational settings."""
    settings, _ = TenantSettings.objects.get_or_create(tenant=tenant)
    for key, value in fields.items():
        setattr(settings, key, value)
    settings.save()
    return settings
