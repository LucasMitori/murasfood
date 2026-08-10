"""Notification endpoints."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import EmailLog, EmailTemplate, Notification, NotificationStatus
from .serializers import EmailLogSerializer, EmailTemplateSerializer, NotificationSerializer


class NotificationViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """The signed-in user's notification centre."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> Any:
        return Notification.objects.filter(
            tenant_id=self.tenant_id, user=self.request.user
        ).order_by("-created_at")

    @extend_schema(request=None, responses={200: dict}, operation_id="notifications_mark_read")
    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request: Request, pk: str | None = None) -> Response:
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.status = NotificationStatus.READ
            notification.save(update_fields=["read_at", "status", "updated_at"])
        return Response({"detail": "read"})

    @extend_schema(request=None, responses={200: dict}, operation_id="notifications_mark_all_read")
    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request: Request) -> Response:
        updated = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(read_at=timezone.now(), status=NotificationStatus.READ)
        )
        return Response({"updated": updated})

    @extend_schema(responses={200: dict}, operation_id="notifications_unread_count")
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})


class EmailTemplateViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Merchant-editable transactional email templates."""

    serializer_class = EmailTemplateSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["tenant.settings"], "default": ["tenant.settings"]}
    filterset_fields = ["key", "locale", "is_active"]
    pagination_class = None

    def get_queryset(self) -> Any:
        return EmailTemplate.objects.for_tenant(self.tenant_id).order_by("key", "locale")

    def perform_update(self, serializer: Any) -> None:
        """Bump the version on every edit, so a bad change is traceable."""
        serializer.save(version=serializer.instance.version + 1)

    @extend_schema(
        request=None, responses={200: dict}, operation_id="email_templates_restore_defaults"
    )
    @action(detail=False, methods=["post"], url_path="restore-defaults")
    def restore_defaults(self, request: Request) -> Response:
        """Re-install any default template the merchant has deleted."""
        from .services import seed_default_templates

        created = seed_default_templates(self.tenant)
        return Response({"created": created})


class EmailLogViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Delivery log — the answer to "did the customer get the email?"."""

    serializer_class = EmailLogSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]
    filterset_fields = ["status", "template_key", "related_type", "related_id"]

    def get_queryset(self) -> Any:
        return EmailLog.objects.for_tenant(self.tenant_id).order_by("-created_at")
