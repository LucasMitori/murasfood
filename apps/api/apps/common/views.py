"""
Shared view infrastructure.

The two base classes here are what keep tenant isolation from being a thing
every developer has to remember. Any viewset inheriting from
:class:`TenantScopedMixin` gets:

* an authoritative ``self.tenant`` resolved *after* authentication,
* a queryset automatically narrowed to that tenant,
* ``tenant`` injected on create,
* a 404 (never a 403) when an object from another tenant is requested, so the
  API does not confirm that the resource exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import CrossTenantAccessError, TenantResolutionError
from .permissions import HasTenantPermission

if TYPE_CHECKING:  # pragma: no cover
    from django.db.models import QuerySet
    from rest_framework.request import Request


class TenantScopedMixin:
    """Resolves and enforces the tenant for a view.

    ``tenant_required = False`` allows endpoints that legitimately work without
    a tenant (platform-level administration).
    """

    tenant_required: bool = True

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)  # type: ignore[misc]

        from apps.tenants.resolver import resolve_tenant_for_request

        tenant = resolve_tenant_for_request(request)
        # Overwrite the middleware's preliminary guess: only now do we know the
        # authenticated user, and a user's own tenant always wins over headers.
        request.tenant = tenant
        request._request.tenant = tenant
        request._request.tenant_id = tenant.pk if tenant else None
        self.tenant = tenant

        if self.tenant_required and tenant is None:
            raise TenantResolutionError()

    @property
    def tenant_id(self) -> Any | None:
        return self.tenant.pk if getattr(self, "tenant", None) else None

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()  # type: ignore[misc]
        if self.tenant is None:
            return queryset.none() if self.tenant_required else queryset
        return queryset.filter(tenant_id=self.tenant.pk)

    def get_object(self) -> Any:
        obj = super().get_object()  # type: ignore[misc]
        obj_tenant_id = getattr(obj, "tenant_id", None)
        if obj_tenant_id is not None and obj_tenant_id != self.tenant_id:
            # Defence in depth: get_queryset already filters, but a subclass
            # overriding it must not be able to leak another tenant's row.
            raise CrossTenantAccessError(
                details={"resource": obj.__class__.__name__, "id": str(obj.pk)}
            )
        return obj

    def perform_create(self, serializer: Any) -> None:
        serializer.save(tenant=self.tenant)


class TenantModelViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Full CRUD, tenant-scoped, permission-code driven."""


class TenantReadOnlyViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only, tenant-scoped."""


class HealthView(APIView):
    """Base for probes: never authenticated, never throttled, never logged."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []


class LivenessView(HealthView):
    """Is the process up? Deliberately touches nothing external.

    A liveness probe that checks the database restarts healthy containers
    during a database blip, turning a small outage into a large one.
    """

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(HealthView):
    """Can the process serve traffic? Checks its hard dependencies."""

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        checks: dict[str, str] = {}
        healthy = True

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc.__class__.__name__}"
            healthy = False

        try:
            cache.set("murasfood:healthcheck", "1", timeout=5)
            checks["cache"] = "ok" if cache.get("murasfood:healthcheck") == "1" else "degraded"
        except Exception as exc:
            checks["cache"] = f"error: {exc.__class__.__name__}"
            healthy = False

        return Response(
            {"status": "ok" if healthy else "unavailable", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SystemDiagnosticsView(TenantScopedMixin, APIView):
    """Live health of the platform, for an operator rather than a monitor.

    Gated on the `system.diagnostics` *capability*, not on a `perm.admin.*`
    page code. Page codes are hierarchical — anything under `perm.admin` is
    granted to every holder of `perm.admin` — so expressing this as a page
    would hand queue depth, storage state and configuration warnings to every
    staff member who can open the dashboard. A capability is granted only where
    it is listed, and it is listed only for administrators.

    Never cached: a stale answer to "is it working right now" is a wrong one.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["system.diagnostics"]

    @extend_schema(responses={200: dict}, operation_id="system_diagnostics")
    def get(self, request: Request) -> Response:
        from .diagnostics import run_diagnostics

        report = run_diagnostics(tenant_id=self.tenant_id)
        response = Response(report)
        response["Cache-Control"] = "no-store"
        return response
