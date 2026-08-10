"""Tenant serializers.

``TenantPublicSerializer`` is what the storefront boots from: it carries every
piece of white-label configuration the frontend needs (branding, locale,
currency, opening hours, legal links) and nothing that is private.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.media.serializers import MediaAssetSerializer

from .models import BusinessHours, Tenant, TenantBranding, TenantSettings


class BusinessHoursSerializer(serializers.ModelSerializer):
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = BusinessHours
        fields = ["id", "weekday", "weekday_label", "opens_at", "closes_at", "is_closed"]
        read_only_fields = ["id"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        opens_at = attrs.get("opens_at")
        closes_at = attrs.get("closes_at")
        if not attrs.get("is_closed") and opens_at and closes_at and closes_at <= opens_at:
            raise serializers.ValidationError(
                {"closes_at": "Closing time must be after opening time."}
            )
        return attrs


class TenantBrandingSerializer(serializers.ModelSerializer):
    logo = MediaAssetSerializer(read_only=True)
    logo_dark = MediaAssetSerializer(read_only=True)
    favicon = MediaAssetSerializer(read_only=True)

    logo_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    logo_dark_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    favicon_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = TenantBranding
        fields = [
            "logo",
            "logo_dark",
            "favicon",
            "logo_id",
            "logo_dark_id",
            "favicon_id",
            "primary_color",
            "secondary_color",
            "accent_color",
            "dark_primary_color",
            "tagline",
            "about",
            "instagram_url",
            "facebook_url",
            "website_url",
        ]


class TenantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSettings
        fields = [
            "order_number_prefix",
            "allow_orders_when_closed",
            "auto_confirm_paid_orders",
            "max_items_per_order",
            "prices_include_tax",
            "default_tax_rate",
            "allow_backorder",
            "low_stock_threshold",
            "notify_on_new_order",
            "email_sender_name",
            "email_reply_to",
            "privacy_policy_url",
            "terms_url",
        ]


class TenantPublicSerializer(serializers.ModelSerializer):
    """Storefront bootstrap payload. Safe to serve to anonymous visitors."""

    branding = TenantBrandingSerializer(read_only=True)
    business_hours = BusinessHoursSerializer(many=True, read_only=True)
    settings = serializers.SerializerMethodField()
    delivery = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "slug",
            "trade_name",
            "support_email",
            "phone",
            "whatsapp",
            "timezone",
            "currency",
            "locale",
            "address",
            "branding",
            "business_hours",
            "settings",
            "delivery",
        ]

    def get_address(self, obj: Tenant) -> dict[str, Any]:
        """Public store address — used for pickup directions and SEO."""
        return {
            "postal_code": obj.postal_code,
            "street": obj.street,
            "number": obj.number,
            "complement": obj.complement,
            "neighborhood": obj.neighborhood,
            "city": obj.city,
            "state": obj.state,
            "country": obj.country,
            "latitude": str(obj.latitude) if obj.latitude is not None else None,
            "longitude": str(obj.longitude) if obj.longitude is not None else None,
        }

    def get_settings(self, obj: Tenant) -> dict[str, Any]:
        """Only the settings a storefront legitimately needs."""
        settings = getattr(obj, "settings", None)
        if settings is None:
            return {}
        return {
            "prices_include_tax": settings.prices_include_tax,
            "allow_orders_when_closed": settings.allow_orders_when_closed,
            "privacy_policy_url": settings.privacy_policy_url,
            "terms_url": settings.terms_url,
        }

    def get_delivery(self, obj: Tenant) -> dict[str, Any]:
        from apps.delivery.selectors import public_delivery_config

        return public_delivery_config(obj)


class TenantAdminSerializer(serializers.ModelSerializer):
    """Full tenant record for merchant administrators."""

    branding = TenantBrandingSerializer(read_only=True)
    settings = TenantSettingsSerializer(read_only=True)
    business_hours = BusinessHoursSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "slug",
            "legal_name",
            "trade_name",
            "tax_id",
            "support_email",
            "phone",
            "whatsapp",
            "postal_code",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "country",
            "latitude",
            "longitude",
            "timezone",
            "currency",
            "locale",
            "status",
            "is_active",
            "custom_domain",
            "branding",
            "settings",
            "business_hours",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "status", "is_active", "created_at", "updated_at"]
