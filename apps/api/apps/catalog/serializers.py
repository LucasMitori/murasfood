"""Catalog serializers.

Two representations of a product exist on purpose:

``ProductListSerializer`` / ``ProductDetailSerializer``
    What a shopper sees. No cost, no margin, no supplier data.

``ProductAdminSerializer``
    What merchant staff see, including cost and stock.

Keeping them separate means a public endpoint cannot leak margin data by
accident.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.common.money import money_str
from apps.common.serializers import MoneySerializerField, QuantitySerializerField
from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetSerializer

from .models import (
    Brand,
    Category,
    CategoryTranslation,
    Favorite,
    Product,
    ProductBarcode,
    ProductImage,
    ProductTag,
    ProductTranslation,
    UnitOfMeasure,
)
from .services import localized_field


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "name", "kind", "precision", "step"]
        read_only_fields = ["id"]


class BrandSerializer(serializers.ModelSerializer):
    logo = MediaAssetSerializer(read_only=True)
    logo_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "description", "logo", "logo_id", "is_active"]
        read_only_fields = ["id", "slug"]


class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = ["id", "name", "slug", "color"]
        read_only_fields = ["id", "slug"]


class CategoryTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryTranslation
        fields = ["locale", "name", "description"]


class ProductTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTranslation
        fields = ["locale", "name", "short_description", "description"]


class LocalizedMixin:
    """Resolves the request locale once for translated fields."""

    def _locale(self) -> str | None:
        request = self.context.get("request")  # type: ignore[attr-defined]
        if request is None:
            return None
        # `Accept-Language` is the standard channel; an explicit `?locale=`
        # wins because the storefront lets a visitor switch language manually.
        explicit = request.query_params.get("locale") if hasattr(request, "query_params") else None
        return explicit or request.headers.get("Accept-Language", "").split(",")[0] or None


class CategorySerializer(LocalizedMixin, serializers.ModelSerializer):
    image = MediaAssetSerializer(read_only=True)
    image_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    children = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True, default=0)
    name = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent",
            "image",
            "image_id",
            "position",
            "is_active",
            "is_featured",
            "children",
            "product_count",
        ]
        read_only_fields = ["id", "slug", "children", "product_count"]

    def get_name(self, obj: Category) -> str:
        return localized_field(obj, "name", self._locale())

    def get_children(self, obj: Category) -> list[dict[str, Any]]:
        children = getattr(obj, "_prefetched_objects_cache", {}).get("children")
        if children is None:
            children = obj.children.filter(is_active=True).order_by("position", "name")
        return CategoryChildSerializer(children, many=True, context=self.context).data


class CategoryChildSerializer(LocalizedMixin, serializers.ModelSerializer):
    """Flat child representation — avoids unbounded recursion."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "position", "is_active"]

    def get_name(self, obj: Category) -> str:
        return localized_field(obj, "name", self._locale())


class ProductImageSerializer(serializers.ModelSerializer):
    asset = MediaAssetSerializer(read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "asset", "position", "is_primary"]
        read_only_fields = ["id"]


class ProductBarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBarcode
        fields = ["id", "code", "barcode_type", "is_primary"]
        read_only_fields = ["id"]


class ProductPriceInfoMixin:
    """Shared price/stock presentation for storefront serializers."""

    def _price_payload(self, obj: Product) -> dict[str, Any]:
        """Read prices from the annotation when present, else query.

        Listing endpoints annotate; a detail endpoint fetching one product can
        afford the extra query.
        """
        base = getattr(obj, "base_price", None)
        effective = getattr(obj, "effective_price", None)

        if effective is None:
            from apps.pricing.selectors import resolve_price

            resolved = resolve_price(obj)
            if resolved is None:
                return {"price": None, "base_price": None, "is_discounted": False, "discount": None}
            base, effective = resolved.base_price, resolved.unit_price

        discounted = base is not None and effective is not None and effective < base
        # `money_str` keeps the scale identical whichever database produced the
        # annotation: PostgreSQL returns 12.50 where SQLite returns 12.5.
        return {
            "price": money_str(effective) if effective is not None else None,
            "base_price": money_str(base) if base is not None else None,
            "is_discounted": discounted,
            "discount": money_str(base - effective) if discounted else None,
        }

    def _stock_payload(self, obj: Product) -> dict[str, Any]:
        """Availability without exposing exact stock levels to customers.

        A competitor should not be able to read a merchant's inventory off the
        public API, so only a coarse flag and a "low stock" hint are published.

        ``waiting`` is the number of people who asked to be told when this comes
        back. It is a count of *demand*, not of stock, and it is published on
        purpose: "14 people are waiting for this" is the social proof that makes
        a shopper leave their address instead of leaving.
        """
        waiting = int(getattr(obj, "restock_waiting", 0) or 0)
        item = getattr(obj, "inventory", None)
        if item is None or not item.track_stock:
            return {"in_stock": True, "low_stock": False, "waiting": waiting}
        available = item.available_quantity
        return {
            "in_stock": available > 0,
            "low_stock": 0 < available <= item.reorder_threshold,
            "waiting": waiting,
        }


class ProductListSerializer(LocalizedMixin, ProductPriceInfoMixin, serializers.ModelSerializer):
    """Product card."""

    name = serializers.SerializerMethodField()
    short_description = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    unit = UnitOfMeasureSerializer(source="sale_unit", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "short_description",
            "image",
            "price",
            "stock",
            "unit",
            "unit_quantity",
            "brand_name",
            "category_slug",
            "product_type",
            "is_featured",
            "is_favorite",
        ]

    def get_name(self, obj: Product) -> str:
        return localized_field(obj, "name", self._locale())

    def get_short_description(self, obj: Product) -> str:
        return localized_field(obj, "short_description", self._locale())

    def get_image(self, obj: Product) -> dict[str, Any] | None:
        image = obj.primary_image
        return MediaAssetSerializer(image.asset).data if image else None

    def get_price(self, obj: Product) -> dict[str, Any]:
        return self._price_payload(obj)

    def get_stock(self, obj: Product) -> dict[str, Any]:
        return self._stock_payload(obj)

    def get_is_favorite(self, obj: Product) -> bool:
        return obj.pk in (self.context.get("favorite_ids") or set())


class ProductDetailSerializer(ProductListSerializer):
    """Product page."""

    description = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    tags = ProductTagSerializer(many=True, read_only=True)
    category = CategoryChildSerializer(read_only=True)
    breadcrumb = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = [
            *ProductListSerializer.Meta.fields,
            "description",
            "images",
            "tags",
            "category",
            "breadcrumb",
            "requires_weighing",
            "requires_age_check",
            "max_quantity_per_order",
        ]

    def get_description(self, obj: Product) -> str:
        return localized_field(obj, "description", self._locale())

    def get_breadcrumb(self, obj: Product) -> list[dict[str, str]]:
        trail = [*obj.category.ancestors(), obj.category]
        return [{"name": node.name, "slug": node.slug} for node in trail]


class ProductAdminSerializer(serializers.ModelSerializer):
    """Merchant view: includes cost, stock and lifecycle fields."""

    images = ProductImageSerializer(many=True, read_only=True)

    #: Write side of ``images``. The nested serializer stays read-only because
    #: what a client sends is a list of already-uploaded assets, not image rows:
    #: the file goes to ``/media/upload/`` first and this attaches the result.
    image_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        required=False,
        queryset=MediaAsset.objects.all(),
        help_text=_("Media assets to show for this product, in order. The first is primary."),
    )

    barcodes = ProductBarcodeSerializer(many=True, read_only=True)
    translations = ProductTranslationSerializer(many=True, required=False)
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ProductTag.objects.all(), required=False
    )

    price = MoneySerializerField(source="effective_price", read_only=True)
    base_price = MoneySerializerField(read_only=True)
    cost_price = MoneySerializerField(read_only=True, allow_null=True)
    stock_quantity = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "slug",
            "short_description",
            "description",
            "category",
            "brand",
            "tags",
            "product_type",
            "sale_unit",
            "unit_quantity",
            "status",
            "is_active",
            "is_featured",
            "requires_weighing",
            "requires_age_check",
            "tax_category",
            "max_quantity_per_order",
            "images",
            "image_ids",
            "barcodes",
            "translations",
            "price",
            "base_price",
            "cost_price",
            "stock_quantity",
            "available_quantity",
            "sales_count",
            "view_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "images",
            "barcodes",
            "sales_count",
            "view_count",
            "created_at",
            "updated_at",
        ]

    def get_stock_quantity(self, obj: Product) -> str | None:
        item = getattr(obj, "inventory", None)
        return str(item.quantity) if item else None

    def get_available_quantity(self, obj: Product) -> str | None:
        item = getattr(obj, "inventory", None)
        return str(item.available_quantity) if item else None

    def update(self, instance: Product, validated_data: dict[str, Any]) -> Product:
        translations = validated_data.pop("translations", None)
        images = validated_data.pop("image_ids", None)
        product = super().update(instance, validated_data)
        if translations is not None:
            self._sync_translations(product, translations)
        # `None` means the client did not mention images; an empty list means it
        # asked for none. Only the second should clear them.
        if images is not None:
            self._sync_images(product, images)
        return product

    def create(self, validated_data: dict[str, Any]) -> Product:
        translations = validated_data.pop("translations", [])
        images = validated_data.pop("image_ids", [])
        product = super().create(validated_data)
        self._sync_translations(product, translations)
        self._sync_images(product, images)
        return product

    @staticmethod
    def _sync_images(product: Product, assets: list[Any]) -> None:
        """Replace the product's images with exactly this list, in this order.

        Rows are rebuilt rather than diffed because position and primacy are
        properties of the *list*, not of any one row: dragging the third image
        to the front changes two rows, and reconciling that is more code than
        writing the four rows again.
        """
        product.images.all().delete()

        ProductImage.objects.bulk_create(
            [
                ProductImage(
                    tenant_id=product.tenant_id,
                    product=product,
                    asset=asset,
                    position=index,
                    # Exactly one primary, and it is the one shown first.
                    is_primary=index == 0,
                )
                for index, asset in enumerate(assets)
            ]
        )

    @staticmethod
    def _sync_translations(product: Product, translations: list[dict[str, Any]]) -> None:
        for item in translations:
            ProductTranslation.objects.update_or_create(
                product=product,
                locale=item["locale"],
                defaults={
                    "tenant_id": product.tenant_id,
                    "name": item.get("name", product.name),
                    "short_description": item.get("short_description", ""),
                    "description": item.get("description", ""),
                },
            )


class ProductCreateSerializer(serializers.Serializer):
    """Explicit creation payload; the service applies the business rules."""

    name = serializers.CharField(max_length=255)
    category = serializers.UUIDField()
    sale_unit = serializers.UUIDField()
    sku = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    short_description = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    brand = serializers.UUIDField(required=False, allow_null=True)
    product_type = serializers.CharField(required=False, default="SIMPLE")
    unit_quantity = QuantitySerializerField(required=False)
    is_featured = serializers.BooleanField(required=False, default=False)
    requires_weighing = serializers.BooleanField(required=False, default=False)

    base_price = MoneySerializerField(required=False, allow_null=True)
    cost_price = MoneySerializerField(required=False, allow_null=True)
    initial_stock = QuantitySerializerField(required=False, allow_null=True)


class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "product", "created_at"]
        read_only_fields = fields


class FavoriteWriteSerializer(serializers.Serializer):
    product = serializers.UUIDField()


class ImageAttachSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    position = serializers.IntegerField(required=False, default=0)
    is_primary = serializers.BooleanField(required=False, default=False)
