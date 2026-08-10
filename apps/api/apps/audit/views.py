"""Audit log reading. There is no write endpoint by design."""

from __future__ import annotations

from typing import Any

from django_filters import rest_framework as filters
from rest_framework import viewsets

from apps.common.pagination import TimelinePagination
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(filters.FilterSet):
    action = filters.CharFilter(lookup_expr="icontains")
    resource_type = filters.CharFilter(lookup_expr="iexact")
    resource_id = filters.CharFilter(lookup_expr="exact")
    actor = filters.UUIDFilter(field_name="actor_id")
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["action", "resource_type", "resource_id", "actor"]


class AuditLogViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["audit.view"]
    pagination_class = TimelinePagination
    filterset_class = AuditLogFilter
    queryset = AuditLog.objects.select_related("actor").all()

    def get_queryset(self) -> Any:
        return super().get_queryset().order_by("-created_at")
