"""Tenant endpoints.

``GET /api/v1/tenants/current/`` is the storefront's first request: it returns
the white-label configuration used to theme the UI before anything else renders.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Prefetch
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.common.exceptions import TenantResolutionError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .models import FaqCategory, FaqEntry, FaqStatus
from .selectors import is_open_at, tenant_with_configuration
from .serializers import (
    BusinessHoursSerializer,
    FaqCategorySerializer,
    FaqEntrySerializer,
    FaqPublicCategorySerializer,
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


class AdminFaqCategoryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Headings on the help page."""

    serializer_class = FaqCategorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["tenant.settings"], "default": ["tenant.settings"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return (
            FaqCategory.objects.for_tenant(self.tenant_id)
            .annotate(entry_count=Count("entries"))
            .order_by("position", "name")
        )

    def perform_create(self, serializer: Any) -> None:
        from apps.catalog.services import unique_slug

        serializer.save(
            tenant=self.tenant,
            slug=unique_slug(FaqCategory, self.tenant_id, serializer.validated_data["name"]),
        )


class AdminFaqEntryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Questions and answers, draft or published."""

    serializer_class = FaqEntrySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["tenant.settings"],
        "retrieve": ["tenant.settings"],
        "default": ["tenant.settings"],
    }
    filterset_fields = ["category", "status"]
    search_fields = ["question", "answer"]

    def get_queryset(self) -> Any:
        return (
            FaqEntry.objects.for_tenant(self.tenant_id)
            .select_related("category")
            .order_by("position", "created_at")
        )

    def perform_create(self, serializer: Any) -> None:
        serializer.save(tenant=self.tenant, updated_by=self.request.user)

    def perform_update(self, serializer: Any) -> None:
        serializer.save(updated_by=self.request.user)

    @extend_schema(request=None, responses=FaqEntrySerializer, operation_id="admin_faq_publish")
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        """Make an answer live, stamping when.

        A separate action rather than a PATCH of `status` so the timestamp
        cannot drift out of step with the state — and so the audit log records
        publishing as its own event rather than as an edit that happened to
        change a field.
        """
        entry = self.get_object()
        entry.status = FaqStatus.PUBLISHED
        entry.published_at = timezone.now()
        entry.updated_by = request.user
        entry.save(update_fields=["status", "published_at", "updated_by", "updated_at"])

        record_audit(
            action="tenant.faq_published",
            tenant=self.tenant,
            actor=request.user,
            resource=entry,
            new_values={"question": entry.question},
            request=request,
        )
        return Response(FaqEntrySerializer(entry).data)

    @extend_schema(request=None, responses=FaqEntrySerializer, operation_id="admin_faq_unpublish")
    @action(detail=True, methods=["post"])
    def unpublish(self, request: Request, pk: str | None = None) -> Response:
        """Back to draft. The copy is kept — this is hiding, not deleting."""
        entry = self.get_object()
        entry.status = FaqStatus.DRAFT
        entry.updated_by = request.user
        entry.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(FaqEntrySerializer(entry).data)

    @extend_schema(request=None, responses={200: dict}, operation_id="admin_faq_reorder")
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request) -> Response:
        """Persist a drag-and-drop ordering in one write."""
        order = request.data.get("order") or []
        entries = {str(entry.pk): entry for entry in self.get_queryset()}

        updated = []
        for index, entry_id in enumerate(order):
            entry = entries.get(str(entry_id))
            if entry is not None:
                entry.position = index
                updated.append(entry)

        if updated:
            FaqEntry.objects.bulk_update(updated, ["position"])
        return Response({"reordered": len(updated)})


class PublicFaqView(TenantScopedMixin, APIView):
    """The help page, as a visitor sees it.

    Published entries only, grouped by heading. An empty list is a valid answer:
    a shop that has written nothing gets the page's built-in copy instead, which
    is what every shop had before this was editable.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses=FaqPublicCategorySerializer(many=True), operation_id="tenants_faq")
    def get(self, request: Request) -> Response:
        published = FaqEntry.objects.filter(status=FaqStatus.PUBLISHED).order_by("position")

        categories = (
            FaqCategory.objects.for_tenant(self.tenant_id)
            .filter(is_active=True)
            .prefetch_related(Prefetch("entries", queryset=published, to_attr="published_entries"))
            .order_by("position", "name")
        )

        # A heading with nothing published under it is noise on a help page.
        visible = [category for category in categories if category.published_entries]
        return Response(FaqPublicCategorySerializer(visible, many=True).data)
