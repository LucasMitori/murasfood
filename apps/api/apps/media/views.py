"""Media, document and banner endpoints."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.common.permissions import HasTenantPermission
from apps.common.serializers import MessageResponseSerializer
from apps.common.views import TenantScopedMixin

from .models import AssetFolder, AssetKind, Banner, Document, MediaAsset
from .serializers import (
    BannerPublicSerializer,
    BannerSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    MediaAssetSerializer,
    MediaUploadSerializer,
)
from .services import create_document, delete_asset, record_banner_event, store_upload


class MediaUploadView(TenantScopedMixin, APIView):
    """Upload an image and receive an asset id to attach elsewhere."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["media.upload"]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=MediaUploadSerializer,
        responses={201: MediaAssetSerializer},
        operation_id="media_upload",
    )
    def post(self, request: Request) -> Response:
        serializer = MediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        folder = serializer.validated_data["folder"]
        if folder not in AssetFolder.values:
            folder = AssetFolder.PRODUCT

        asset = store_upload(
            tenant=self.tenant,
            upload=serializer.validated_data["file"],
            folder=folder,
            kind=AssetKind.IMAGE,
            alt_text=serializer.validated_data["alt_text"],
            is_public=True,
            uploaded_by=request.user,
        )
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class MediaAssetViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Browse and remove uploaded assets."""

    serializer_class = MediaAssetSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"destroy": ["media.upload"], "default": ["catalog.view"]}
    queryset = MediaAsset.objects.all()
    filterset_fields = ["folder", "kind", "status"]

    @extend_schema(responses={204: None}, operation_id="media_delete")
    @action(detail=True, methods=["delete"])
    def remove(self, request: Request, pk: str | None = None) -> Response:
        asset = self.get_object()
        record_audit(
            action="media.deleted",
            tenant=self.tenant,
            actor=request.user,
            resource=asset,
            request=request,
        )
        delete_asset(asset)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Private documents. Every download goes through a signed URL."""

    serializer_class = DocumentSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["documents.view"],
        "retrieve": ["documents.view"],
        "create": ["documents.upload"],
        "destroy": ["documents.delete"],
        "default": ["documents.view"],
    }
    parser_classes = [MultiPartParser, FormParser]
    queryset = Document.objects.select_related("asset").all()
    filterset_fields = ["document_type", "related_type", "related_id"]

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={201: DocumentSerializer},
        operation_id="documents_create",
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document = create_document(
            tenant=self.tenant, uploaded_by=request.user, **serializer.validated_data
        )
        record_audit(
            action="document.uploaded",
            tenant=self.tenant,
            actor=request.user,
            resource=document,
            new_values={"title": document.title, "type": document.document_type},
            request=request,
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Document) -> None:
        record_audit(
            action="document.deleted",
            tenant=self.tenant,
            actor=self.request.user,
            resource=instance,
            old_values={"title": instance.title, "type": instance.document_type},
            request=self.request,
        )
        asset = instance.asset
        instance.delete()
        delete_asset(asset)


class BannerViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Banner management for merchant staff."""

    serializer_class = BannerSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["catalog.view"], "default": ["catalog.update"]}
    queryset = Banner.objects.select_related("image", "mobile_image").all()
    filterset_fields = ["is_active", "link_type"]


class PublicBannerListView(TenantScopedMixin, APIView):
    """Banners currently live on the storefront."""

    permission_classes = [AllowAny]

    @extend_schema(responses=BannerPublicSerializer(many=True), operation_id="banners_public_list")
    def get(self, request: Request) -> Response:
        now = timezone.now()
        banners = (
            Banner.objects.for_tenant(self.tenant_id)
            .select_related("image", "mobile_image")
            .filter(is_active=True)
            .filter(models_q_live(now))
            .order_by("-priority", "-created_at")[:12]
        )
        return Response(BannerPublicSerializer(banners, many=True).data)


class BannerEventView(TenantScopedMixin, APIView):
    """Records an impression or a click. Fire-and-forget from the client."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={202: MessageResponseSerializer},
        operation_id="banners_record_event",
    )
    def post(self, request: Request, pk: str, event: str) -> Response:
        if event not in {"impression", "click"}:
            return Response({"detail": "Unknown event."}, status=status.HTTP_400_BAD_REQUEST)
        if Banner.objects.for_tenant(self.tenant_id).filter(pk=pk).exists():
            record_banner_event(pk, event=event)
        return Response({"detail": "recorded"}, status=status.HTTP_202_ACCEPTED)


def models_q_live(now: Any) -> Any:
    """``Q`` matching banners whose schedule window contains ``now``."""
    from django.db.models import Q

    return (Q(start_at__isnull=True) | Q(start_at__lte=now)) & (
        Q(end_at__isnull=True) | Q(end_at__gte=now)
    )
