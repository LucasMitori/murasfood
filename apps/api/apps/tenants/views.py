"""Tenant endpoints.

``GET /api/v1/tenants/current/`` is the storefront's first request: it returns
the white-label configuration used to theme the UI before anything else renders.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.common.exceptions import TenantResolutionError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .selectors import is_open_at, tenant_with_configuration
from .serializers import (
    BusinessHoursSerializer,
    TenantAdminSerializer,
    TenantBrandingSerializer,
    TenantPublicSerializer,
    TenantSettingsSerializer,
)
from .services import update_branding, update_settings


class CurrentTenantView(TenantScopedMixin, APIView):
    """Public white-label configuration for the resolved tenant."""

    permission_classes = [AllowAny]

    @extend_schema(responses=TenantPublicSerializer, operation_id="tenants_current")
    def get(self, request: Request) -> Response:
        tenant = tenant_with_configuration(self.tenant_id)
        if tenant is None:
            raise TenantResolutionError()

        payload = TenantPublicSerializer(tenant).data
        payload["is_open_now"] = is_open_at(tenant)
        return Response(payload)


class TenantAdminView(TenantScopedMixin, APIView):
    """Merchant-facing view of the tenant record."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    @extend_schema(responses=TenantAdminSerializer, operation_id="tenants_admin_retrieve")
    def get(self, request: Request) -> Response:
        tenant = tenant_with_configuration(self.tenant_id)
        return Response(TenantAdminSerializer(tenant).data)

    @extend_schema(
        request=TenantAdminSerializer,
        responses=TenantAdminSerializer,
        operation_id="tenants_admin_update",
    )
    def patch(self, request: Request) -> Response:
        serializer = TenantAdminSerializer(self.tenant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = TenantAdminSerializer(self.tenant).data
        tenant = serializer.save()

        record_audit(
            action="tenant.updated",
            tenant=tenant,
            actor=request.user,
            resource=tenant,
            old_values=before,
            new_values=serializer.data,
            request=request,
        )
        return Response(TenantAdminSerializer(tenant_with_configuration(tenant.pk)).data)


class TenantBrandingView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.branding"]

    @extend_schema(
        request=TenantBrandingSerializer,
        responses=TenantBrandingSerializer,
        operation_id="tenants_branding_update",
    )
    def patch(self, request: Request) -> Response:
        serializer = TenantBrandingSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        branding = update_branding(self.tenant, **serializer.validated_data)

        record_audit(
            action="tenant.branding_updated",
            tenant=self.tenant,
            actor=request.user,
            resource=branding,
            new_values=serializer.validated_data,
            request=request,
        )
        return Response(TenantBrandingSerializer(branding).data)


class TenantSettingsView(TenantScopedMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    @extend_schema(
        request=TenantSettingsSerializer,
        responses=TenantSettingsSerializer,
        operation_id="tenants_settings_update",
    )
    def patch(self, request: Request) -> Response:
        serializer = TenantSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings = update_settings(self.tenant, **serializer.validated_data)

        record_audit(
            action="tenant.settings_updated",
            tenant=self.tenant,
            actor=request.user,
            resource=settings,
            new_values=serializer.validated_data,
            request=request,
        )
        return Response(TenantSettingsSerializer(settings).data)


class BusinessHoursView(TenantScopedMixin, APIView):
    """Replaces the whole weekly schedule in one call.

    Editing hours piecemeal invites inconsistent states (two overlapping
    windows, a missing close time), so the client always submits the full week.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    @extend_schema(
        request=BusinessHoursSerializer(many=True),
        responses=BusinessHoursSerializer(many=True),
        operation_id="tenants_business_hours_replace",
    )
    def put(self, request: Request) -> Response:
        serializer = BusinessHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        self.tenant.business_hours.all().delete()
        created: list[Any] = [
            self.tenant.business_hours.create(**item) for item in serializer.validated_data
        ]

        record_audit(
            action="tenant.business_hours_updated",
            tenant=self.tenant,
            actor=request.user,
            resource=self.tenant,
            new_values={"windows": len(created)},
            request=request,
        )
        return Response(BusinessHoursSerializer(created, many=True).data, status=status.HTTP_200_OK)
