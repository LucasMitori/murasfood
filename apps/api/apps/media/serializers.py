"""Media serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Banner, Document, MediaAsset
from .services import asset_url


class MediaAssetSerializer(serializers.ModelSerializer):
    """An asset plus the URLs a client can actually render.

    ``variants`` gives the frontend a responsive ``srcset`` without it needing
    to know how keys are built.
    """

    url = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            "id",
            "kind",
            "status",
            "url",
            "variants",
            "alt_text",
            "width",
            "height",
            "size_bytes",
            "content_type",
            "original_filename",
            "created_at",
        ]
        read_only_fields = fields

    def get_url(self, obj: MediaAsset) -> str:
        return asset_url(obj)

    def get_variants(self, obj: MediaAsset) -> dict[str, str]:
        if not obj.derivatives:
            return {}
        return {name: asset_url(obj, variant=name) for name in obj.derivatives}


class MediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    folder = serializers.CharField(required=False, default="products")
    alt_text = serializers.CharField(required=False, allow_blank=True, default="")


class DocumentSerializer(serializers.ModelSerializer):
    asset = MediaAssetSerializer(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "document_type",
            "title",
            "description",
            "related_type",
            "related_id",
            "asset",
            "download_url",
            "created_at",
        ]
        read_only_fields = ["id", "asset", "download_url", "created_at"]

    def get_download_url(self, obj: Document) -> str:
        """Signed, short-lived URL. Private documents are never public."""
        return asset_url(obj.asset)


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(max_length=255)
    document_type = serializers.CharField(max_length=24, required=False, default="OTHER")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    related_type = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    related_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class BannerSerializer(serializers.ModelSerializer):
    image = MediaAssetSerializer(read_only=True)
    mobile_image = MediaAssetSerializer(read_only=True)
    image_id = serializers.UUIDField(write_only=True)
    mobile_image_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Banner
        fields = [
            "id",
            "title",
            "subtitle",
            "image",
            "mobile_image",
            "image_id",
            "mobile_image_id",
            "link_type",
            "link_target",
            "start_at",
            "end_at",
            "priority",
            "is_active",
            "impression_count",
            "click_count",
            "created_at",
        ]
        read_only_fields = ["id", "impression_count", "click_count", "created_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        from .services import validate_banner_link

        link_type = attrs.get("link_type", getattr(self.instance, "link_type", "NONE"))
        link_target = attrs.get("link_target", getattr(self.instance, "link_target", ""))
        attrs["link_target"] = validate_banner_link(link_type, link_target)

        start_at, end_at = attrs.get("start_at"), attrs.get("end_at")
        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "The end date must be after the start."})
        return attrs


class BannerPublicSerializer(serializers.ModelSerializer):
    """What the storefront receives: no counters, no scheduling internals."""

    image = MediaAssetSerializer(read_only=True)
    mobile_image = MediaAssetSerializer(read_only=True)

    class Meta:
        model = Banner
        fields = ["id", "title", "subtitle", "image", "mobile_image", "link_type", "link_target"]
        read_only_fields = fields
