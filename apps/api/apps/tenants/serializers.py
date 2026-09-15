"""Tenant serializers.

``TenantPublicSerializer`` is what the storefront boots from: it carries every
piece of white-label configuration the frontend needs (branding, locale,
currency, opening hours, legal links) and nothing that is private.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.media.serializers import MediaAssetSerializer

from .models import (
    FLOATING_POSITIONS,
    FLOATING_TOOL_KEYS,
    HOME_SECTION_KEYS,
    HOME_SECTION_MAX_LIMIT,
    PARALLAX_HEIGHTS,
    PARALLAX_MAX_BANDS,
    BusinessHours,
    FaqCategory,
    FaqEntry,
    FaqStatus,
    Tenant,
    TenantBranding,
    TenantSettings,
    is_parallax,
)


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
    """Merchant-editable settings.

    `floating_tools` is validated rather than trusted: it is free-form JSON in
    the database, so without a check a typo in a tool name would be stored
    happily and then silently drop that shortcut from the storefront.
    """

    #: Accepted but never returned. A password the API hands back is a password
    #: in every browser cache and log that ever saw the response.
    smtp_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )

    #: So the interface can say "a password is set" without being told what it
    #: is, and can leave it alone rather than clearing it on every save.
    smtp_password_set = serializers.SerializerMethodField()

    def get_smtp_password_set(self, obj: TenantSettings) -> bool:
        return bool(obj.smtp_password)

    def validate_floating_tools(self, value: Any) -> dict:
        return _validate_floating_tools(value)

    def validate_home_layout(self, value: Any) -> list[dict]:
        return _validate_home_layout(value)

    def validate_hero(self, value: Any) -> dict:
        return _validate_hero(value)

    def update(self, instance: TenantSettings, validated_data: dict) -> TenantSettings:
        """An omitted password means "leave it"; an empty one means "clear it".

        Without this an edit to any other field would blank the password,
        because a form that does not know the secret cannot send it back.
        """
        if "smtp_password" not in self.initial_data:
            validated_data.pop("smtp_password", None)

        return super().update(instance, validated_data)

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
            "hide_out_of_stock",
            "notify_on_new_order",
            "email_sender_name",
            "email_reply_to",
            "privacy_policy_url",
            "terms_url",
            "floating_tools",
            "home_layout",
            "hero",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "smtp_use_tls",
            "smtp_from_email",
            "smtp_password_set",
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
            # The storefront needs this to draw its floating button at all.
            # Without it the merchant's choices are stored and never read, and
            # the button silently falls back to showing everything.
            "floating_tools": settings.floating_tools,
            # Same reasoning: the dashboard's layout editor reads the tenant
            # through this serializer, so omitting it here would leave that
            # screen permanently showing the default order no matter what was
            # saved. Not sensitive either way — it describes a public page.
            "home_layout": settings.home_layout,
            "hero": settings.hero,
            # Third time this allow-list has needed remembering (floating_tools,
            # then home_layout). The storefront decides whether to offer a
            # "tell me when it is back" button from this flag, so leaving it out
            # would store the merchant's choice and never act on it.
            "hide_out_of_stock": settings.hide_out_of_stock,
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


def _validate_home_layout(value: Any) -> list[dict]:
    """Check the shape of the home page layout.

    Order is the substance here — it is the order the page renders in — so this
    is a list and the client's order is preserved exactly.

    Two kinds of entry share it. **Rails** are the fixed vocabulary of product
    bands; every one must appear exactly once, because a missing key would
    silently remove a band with no way to bring it back and a repeated one would
    render the same rail twice. **Parallax bands** are the shop's own content
    and are free-form: nought to six of them, wherever they were dropped.

    They live in one list rather than two interleaved by a position field. The
    order *is* the page, and expressing one order as two lists plus an index is
    the same information stated in a way that can disagree with itself.

    An empty `title` on a rail is meaningful and kept: it means "use the
    translated heading", so a shop that never renames a band still reads
    correctly in every language rather than in whichever one the owner happened
    to be using. A parallax band has no translated fallback — it is the
    merchant's own words — so an empty title there simply renders nothing.
    """
    if not isinstance(value, list):
        raise serializers.ValidationError(_("Expected a list."))

    keys = [section.get("key") if isinstance(section, dict) else None for section in value]

    rails = [key for key in keys if not is_parallax(str(key))]
    bands = [key for key in keys if is_parallax(str(key))]

    unknown = [key for key in rails if key not in HOME_SECTION_KEYS]
    if unknown:
        raise serializers.ValidationError(
            _("Unknown sections: %(keys)s") % {"keys": ", ".join(map(str, unknown))}
        )

    if len(set(keys)) != len(keys):
        raise serializers.ValidationError(_("A section cannot be listed twice."))

    missing = [key for key in HOME_SECTION_KEYS if key not in rails]
    if missing:
        raise serializers.ValidationError(
            _("Missing sections: %(keys)s") % {"keys": ", ".join(missing)}
        )

    if len(bands) > PARALLAX_MAX_BANDS:
        raise serializers.ValidationError(
            _("At most %(max)s parallax bands.") % {"max": PARALLAX_MAX_BANDS}
        )

    cleaned = []
    for section in value:
        key = str(section.get("key", ""))

        if is_parallax(key):
            cleaned.append(_clean_parallax(section, key))
            continue

        try:
            limit = int(section.get("limit", 12))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"limit": _("Expected a whole number.")}) from None

        if not 1 <= limit <= HOME_SECTION_MAX_LIMIT:
            raise serializers.ValidationError(
                {"limit": _("Between 1 and %(max)s.") % {"max": HOME_SECTION_MAX_LIMIT}}
            )

        cleaned.append(
            {
                "key": key,
                "enabled": bool(section.get("enabled", True)),
                "title": str(section.get("title") or "")[:80],
                "limit": limit,
            }
        )

    return cleaned


ALIGNMENTS = ("start", "center", "end")


def _clean_parallax(section: dict, key: str) -> dict:
    """One merchant-authored band.

    Everything here is copy the shop wrote, so the only rules are the ones that
    protect the page: a height it was designed for, a link that cannot carry a
    script, and lengths that cannot break the layout.
    """
    try:
        height = int(section.get("height", 70))
    except (TypeError, ValueError):
        raise serializers.ValidationError({"height": _("Expected a whole number.")}) from None

    if height not in PARALLAX_HEIGHTS:
        raise serializers.ValidationError(
            {"height": _("Use %(allowed)s.") % {"allowed": " or ".join(map(str, PARALLAX_HEIGHTS))}}
        )

    try:
        overlay = int(section.get("overlay", 45))
    except (TypeError, ValueError):
        raise serializers.ValidationError({"overlay": _("Expected a whole number.")}) from None

    if not 0 <= overlay <= 90:
        raise serializers.ValidationError({"overlay": _("Between 0 and 90.")})

    # `javascript:` and `data:` in a link the merchant controls would be stored
    # XSS against their own customers. Internal paths and http(s) only.
    cta_url = str(section.get("cta_url") or "").strip()
    if cta_url and not (cta_url.startswith("/") or cta_url.startswith(("http://", "https://"))):
        raise serializers.ValidationError(
            {"cta_url": _("Use a path starting with / or a full http(s) address.")}
        )

    image_id = section.get("image_id") or None
    if image_id is not None:
        try:
            image_id = str(uuid.UUID(str(image_id)))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"image_id": _("Not a valid id.")}) from None

    return {
        "key": key,
        "enabled": bool(section.get("enabled", True)),
        "title": str(section.get("title") or "")[:120],
        "subtitle": str(section.get("subtitle") or "")[:240],
        "cta_label": str(section.get("cta_label") or "")[:40],
        "cta_url": cta_url[:512],
        "image_id": image_id,
        "height": height,
        "overlay": overlay,
        "align": (section.get("align") if section.get("align") in ALIGNMENTS else "center"),
    }


def _validate_hero(value: Any) -> dict:
    """The banner carousel's own behaviour.

    Not a band in the layout list: the hero is always first, and a shop with no
    banners still gets it (falling back to its own name).
    """
    if not isinstance(value, dict):
        raise serializers.ValidationError(_("Expected an object."))

    try:
        overlay = int(value.get("overlay", 45))
    except (TypeError, ValueError):
        raise serializers.ValidationError({"overlay": _("Expected a whole number.")}) from None

    if not 0 <= overlay <= 90:
        raise serializers.ValidationError({"overlay": _("Between 0 and 90.")})

    return {
        "parallax": bool(value.get("parallax", False)),
        "full_height": bool(value.get("full_height", False)),
        "overlay": overlay,
    }


def _validate_floating_tools(value: Any) -> dict:
    """Check the shape of the floating-button configuration.

    Order matters and duplicates do not, so `actions` is a list rather than a
    set — but a repeated key would render the same shortcut twice, so it is
    refused rather than de-duplicated silently.
    """
    if not isinstance(value, dict):
        raise serializers.ValidationError(_("Expected an object."))

    actions = value.get("actions", [])
    if not isinstance(actions, list):
        raise serializers.ValidationError({"actions": _("Expected a list.")})

    unknown = [key for key in actions if key not in FLOATING_TOOL_KEYS]
    if unknown:
        raise serializers.ValidationError(
            {"actions": _("Unknown tools: %(keys)s") % {"keys": ", ".join(map(str, unknown))}}
        )

    if len(set(actions)) != len(actions):
        raise serializers.ValidationError({"actions": _("A tool cannot be listed twice.")})

    position = value.get("position", "bottom-right")
    if position not in FLOATING_POSITIONS:
        raise serializers.ValidationError({"position": _("Unknown position.")})

    return {
        "enabled": bool(value.get("enabled", True)),
        "icon": str(value.get("icon") or "mdi-apps")[:64],
        "color": str(value.get("color") or "primary")[:32],
        "position": position,
        "actions": actions,
    }


class FaqEntrySerializer(serializers.ModelSerializer):
    """One question, as the merchant edits it."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = FaqEntry
        fields = [
            "id",
            "category",
            "category_name",
            "question",
            "answer",
            "status",
            "position",
            "view_count",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "view_count", "published_at", "created_at", "updated_at"]

    def validate_category(self, value: Any) -> Any:
        """A category from another shop would be a cross-tenant write.

        `category` is a plain primary-key field, so without this any id in the
        table is accepted — the queryset scoping on the viewset governs what can
        be *read*, not what can be pointed at.
        """
        tenant_id = getattr(self.context.get("request"), "tenant_id", None)
        if tenant_id and value.tenant_id != tenant_id:
            raise serializers.ValidationError(_("Unknown category."))
        return value


class FaqCategorySerializer(serializers.ModelSerializer):
    entry_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = FaqCategory
        fields = ["id", "name", "slug", "icon", "position", "is_active", "entry_count"]
        read_only_fields = ["id", "slug", "entry_count"]


class FaqPublicCategorySerializer(serializers.ModelSerializer):
    """What the storefront renders. Published entries only."""

    entries = serializers.SerializerMethodField()

    class Meta:
        model = FaqCategory
        fields = ["id", "name", "slug", "icon", "entries"]

    def get_entries(self, obj: FaqCategory) -> list[dict[str, Any]]:
        # Read from the prefetch rather than querying per category: a help page
        # with eight headings would otherwise be nine queries.
        entries = getattr(obj, "published_entries", None)
        if entries is None:
            entries = obj.entries.filter(status=FaqStatus.PUBLISHED).order_by("position")

        return [
            {"id": str(entry.pk), "question": entry.question, "answer": entry.answer}
            for entry in entries
        ]
