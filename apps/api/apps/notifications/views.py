"""Notification endpoints."""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import EmailLog, EmailTemplate, Notification, NotificationStatus
from .serializers import EmailLogSerializer, EmailTemplateSerializer, NotificationSerializer
from .services import _base_context, connection_for, render_template


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


class EmailTemplatePreviewView(TenantScopedMixin, APIView):
    """Render one template with sample values.

    Templates are edited as raw HTML with `{{ placeholders }}`, which is not
    something anyone can read a result from. This substitutes plausible values
    so the merchant sees the message rather than the source.

    Sample data, never real: previewing a template must not require finding an
    order that happens to exercise it, and must not put one customer's details
    on another operator's screen.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    #: One value per placeholder the seeded templates use.
    SAMPLES: dict[str, str] = {
        "first_name": "Maria",
        "order_number": "MF-260101-EXEMPLO",
        "order_total": "R$ 128,40",
        "order_url": "https://exemplo.murasfood.app/account/orders/MF-260101-EXEMPLO",
        "verification_url": "https://exemplo.murasfood.app/auth/verify-email?token=exemplo",
        "reset_url": "https://exemplo.murasfood.app/auth/reset-password?token=exemplo",
        "expires_in_hours": "24",
        "product_name": "Café Torrado 500g",
        "quantity": "3",
    }

    @extend_schema(responses={200: dict}, operation_id="admin_email_template_preview")
    def post(self, request: Request, pk: str) -> Response:
        template = EmailTemplate.objects.filter(pk=pk, tenant_id=self.tenant_id).first()
        if template is None:
            raise NotFoundError()

        # Anything the caller supplies wins, so an operator can see how a real
        # value looks without saving it anywhere.
        context = {**self.SAMPLES, **(request.data.get("context") or {})}
        merged = {**_base_context(self.tenant), **context}

        return Response(
            {
                "subject": render_template(template.subject, merged, escape=False),
                "html": render_template(template.html_body, merged),
                "text": render_template(template.text_body or "", merged, escape=False),
                "context": context,
            }
        )


class EmailTemplateTestView(TenantScopedMixin, APIView):
    """Send one template to an address, to prove the wiring works.

    The point is the *connection*, not the copy: a template that renders
    perfectly still fails if the host, port or credentials are wrong, and the
    only way to know is to send something.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["tenant.settings"]

    @extend_schema(request=dict, responses={200: dict}, operation_id="admin_email_template_test")
    def post(self, request: Request, pk: str) -> Response:
        recipient = (request.data.get("recipient") or "").strip()
        if not recipient:
            raise ValidationError({"recipient": _("An address is required.")})

        template = EmailTemplate.objects.filter(pk=pk, tenant_id=self.tenant_id).first()
        if template is None:
            raise NotFoundError()

        context = {**EmailTemplatePreviewView.SAMPLES, **(request.data.get("context") or {})}
        merged = {**_base_context(self.tenant), **context}

        subject = render_template(template.subject, merged, escape=False)
        html_body = render_template(template.html_body, merged)
        text_body = render_template(template.text_body or "", merged, escape=False)

        row = getattr(self.tenant, "settings", None)
        sender = (row.email_sender_name if row else "") or self.tenant.trade_name
        address = (row.smtp_from_email if row else "") or settings.DEFAULT_FROM_EMAIL

        message = EmailMultiAlternatives(
            subject=f"[teste] {subject}",
            body=text_body or re.sub(r"<[^>]+>", " ", html_body),
            from_email=f"{sender} <{address}>",
            to=[recipient],
            connection=connection_for(self.tenant),
        )
        message.attach_alternative(html_body, "text/html")

        try:
            message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - the reason is the whole point
            # Reported rather than raised: a failed test is a *result*, and the
            # operator needs the server's own words to fix their settings.
            return Response({"sent": False, "detail": str(exc)[:400]}, status=200)

        return Response({"sent": True, "detail": ""})
