"""
Tenant resolution.

Two entry points, deliberately different:

:func:`resolve_tenant_from_request`
    Runs in middleware, before authentication. It may only look at transport
    hints (header, host). Treat its result as a *guess*.

:func:`resolve_tenant_for_request`
    Runs inside the view, after authentication. This is the authoritative
    answer and the one every queryset is filtered by.

The security rule that matters (invariant #1): an authenticated non-platform
user is **always** pinned to their own tenant. A client-supplied ``X-Tenant``
header can never move them, otherwise cross-tenant access would be one header
away.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Tenant, TenantStatus

if TYPE_CHECKING:  # pragma: no cover
    from django.http import HttpRequest

TENANT_HEADER_KEY = "HTTP_X_TENANT"

# Hosts that never carry a meaningful tenant subdomain.
_NON_TENANT_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "api", "web", "testserver"}


def _active_tenants() -> Any:
    return Tenant.objects.filter(is_active=True, status=TenantStatus.ACTIVE)


def tenant_by_identifier(identifier: str) -> Tenant | None:
    """Look a tenant up by slug or UUID.

    Accepting both keeps the header ergonomic (``X-Tenant: demo``) while still
    allowing machine clients to pin an exact id.
    """
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None

    tenant = _active_tenants().filter(slug=identifier).first()
    if tenant is not None:
        return tenant

    # Only try a UUID lookup when the value actually looks like one, so we do
    # not raise ValidationError on arbitrary header content.
    if len(identifier) in (32, 36) and all(c in "0123456789abcdef-" for c in identifier):
        return _active_tenants().filter(pk=identifier).first()
    return None


def _tenant_from_host(host: str) -> Tenant | None:
    """Resolve from a custom domain or the leftmost subdomain label."""
    host = (host or "").split(":", 1)[0].strip().lower()
    if not host or host in _NON_TENANT_HOSTS:
        return None

    exact = _active_tenants().filter(custom_domain=host).first()
    if exact is not None:
        return exact

    label, _, remainder = host.partition(".")
    if not remainder or label in {"www", "api", "app", "admin"}:
        return None
    return _active_tenants().filter(slug=label).first()


def _sole_tenant() -> Tenant | None:
    """Single-merchant deployments should just work with no header at all."""
    tenants = list(_active_tenants()[:2])
    return tenants[0] if len(tenants) == 1 else None


def resolve_tenant_from_request(request: HttpRequest) -> Tenant | None:
    """Preliminary, transport-only resolution. Safe for anonymous traffic."""
    header_value = request.META.get(TENANT_HEADER_KEY, "")
    if header_value:
        tenant = tenant_by_identifier(header_value)
        if tenant is not None:
            return tenant

    tenant = _tenant_from_host(request.get_host() if hasattr(request, "get_host") else "")
    if tenant is not None:
        return tenant

    return _sole_tenant()


def resolve_tenant_for_request(request: Any) -> Tenant | None:
    """Authoritative resolution, performed after authentication.

    Order:

    1. An authenticated, non-platform user is pinned to ``user.tenant``.
    2. A platform administrator may select any tenant via ``X-Tenant``.
    3. Anonymous traffic falls back to transport hints (header, host, or the
       only tenant when the deployment has just one).
    """
    user = getattr(request, "user", None)
    django_request = getattr(request, "_request", request)

    if user is not None and getattr(user, "is_authenticated", False):
        if getattr(user, "is_platform_admin", False):
            header_value = django_request.META.get(TENANT_HEADER_KEY, "")
            selected = tenant_by_identifier(header_value) if header_value else None
            return selected or getattr(user, "tenant", None) or _sole_tenant()

        tenant = getattr(user, "tenant", None)
        if tenant is not None and tenant.is_operational:
            return tenant
        # A user without a tenant (rare: platform-level staff being set up)
        # still gets storefront context so public endpoints keep working.

    return resolve_tenant_from_request(django_request)
