"""Catalog endpoints: public storefront reads and merchant management."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.common import spreadsheets
from apps.common.exceptions import NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.views import TenantScopedMixin

from .filters import ProductFilter
from .models import Brand, Category, Favorite, Product, ProductTag, UnitOfMeasure
from .search import order_by_relevance, search_products, search_suggestions
from .selectors import (
    admin_products,
    apply_sort,
    best_sellers,
    category_tree,
    discounted_products,
    favorite_product_ids,
    featured_products,
    new_arrivals,
    product_by_barcode,
    related_products,
    storefront_products,
)
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    FavoriteSerializer,
    FavoriteWriteSerializer,
    ImageAttachSerializer,
    ProductAdminSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductTagSerializer,
    UnitOfMeasureSerializer,
)
from .services import (
    archive_product,
    attach_image,
    create_product,
    publish_product,
    register_product_view,
    reorder_images,
    toggle_favorite,
    unique_slug,
)


class FavoriteContextMixin:
    """Adds the current customer's favourite ids to the serializer context.

    One query per request instead of one per product card.
    """

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()  # type: ignore[misc]
        context["favorite_ids"] = favorite_product_ids(
            getattr(self.request, "user", None),
            self.tenant_id,  # type: ignore[attr-defined]
        )
        return context


# =============================================================================
# Storefront
# =============================================================================
class ProductViewSet(FavoriteContextMixin, TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Public product catalog. Lookup is by slug for clean, indexable URLs."""

    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    lookup_field = "slug"
    lookup_value_regex = "[^/]+"

    def get_queryset(self) -> Any:
        return storefront_products(self.tenant_id)

    def get_serializer_class(self) -> Any:
        return ProductDetailSerializer if self.action == "retrieve" else ProductListSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Free-text search term"),
            OpenApiParameter(
                "sort",
                str,
                description="relevance | name | -name | price | -price | newest | best_sellers",
            ),
            OpenApiParameter("locale", str, description="Preferred content language"),
        ],
        responses=ProductListSerializer(many=True),
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())

        term = request.query_params.get("q")
        if term:
            queryset = search_products(queryset, term)

        sort = request.query_params.get("sort")
        queryset = order_by_relevance(queryset) if term and not sort else apply_sort(queryset, sort)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        return (
            self.get_paginated_response(serializer.data)
            if page is not None
            else Response(serializer.data)
        )

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        product = self.get_object()
        register_product_view(product)
        return Response(self.get_serializer(product).data)

    @extend_schema(responses=ProductListSerializer(many=True), operation_id="catalog_related")
    @action(detail=True, methods=["get"])
    def related(self, request: Request, slug: str | None = None) -> Response:
        product = self.get_object()
        products = related_products(product)
        return Response(self.get_serializer(products, many=True).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("days", int, description="Window to chart, 1-365. Defaults to 90.")
        ],
        responses={200: dict},
        operation_id="catalog_price_history",
    )
    @action(detail=True, methods=["get"], url_path="price-history")
    def price_history(self, request: Request, slug: str | None = None) -> Response:
        """Shelf-price movement for the chart on the product page.

        Public, and it lives on this viewset rather than in `pricing` for two
        reasons: `get_object()` applies the storefront's own visibility rules,
        so an unpublished product's prices cannot be read through it, and the
        selector returns dated shelf prices only — never cost or margin, which
        the staff endpoint at `/admin/prices/history/` does return.
        """
        from apps.pricing.selectors import public_price_series

        product = self.get_object()
        try:
            days = int(request.query_params.get("days", 90))
        except (TypeError, ValueError):
            days = 90

        return Response(public_price_series(product, days=days))


class StorefrontHomeView(TenantScopedMixin, APIView):
    """One request that fills the home page.

    The storefront's first paint needs banners, categories and several product
    rails. Serving them together avoids a waterfall of round trips on mobile.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict}, operation_id="catalog_home")
    def get(self, request: Request) -> Response:
        from django.utils import timezone

        from apps.media.models import Banner
        from apps.media.serializers import BannerPublicSerializer
        from apps.media.views import models_q_live

        context = {
            "request": request,
            "favorite_ids": favorite_product_ids(request.user, self.tenant_id),
        }

        banners = (
            Banner.objects.for_tenant(self.tenant_id)
            .select_related("image", "mobile_image")
            .filter(is_active=True)
            .filter(models_q_live(timezone.now()))
            .order_by("-priority")[:8]
        )

        def cards(queryset: Any) -> list[dict[str, Any]]:
            return ProductListSerializer(queryset, many=True, context=context).data

        # The merchant decides which rails appear, in what order, how long, and
        # under what heading. Applying it here rather than in the client means a
        # rail nobody will render is never queried or serialised — and the
        # preview in the dashboard reads the same endpoint, so it cannot drift
        # from the real page.
        layout = self._layout()
        sources = {
            "featured": featured_products,
            "on_sale": discounted_products,
            "best_sellers": best_sellers,
            "new_arrivals": new_arrivals,
        }

        payload: dict[str, Any] = {
            "banners": BannerPublicSerializer(banners, many=True).data,
            "layout": self._with_images(layout),
            "hero": getattr(getattr(self.tenant, "settings", None), "hero", None) or {},
            "categories": [],
            "featured": [],
            "on_sale": [],
            "best_sellers": [],
            "new_arrivals": [],
        }

        for section in layout:
            if not section["enabled"]:
                continue

            key = section["key"]
            if key == "categories":
                payload["categories"] = CategorySerializer(
                    category_tree(self.tenant_id), many=True, context=context
                ).data
            elif key in sources:
                payload[key] = cards(sources[key](self.tenant_id, limit=section["limit"]))

        return Response(payload)

    def _with_images(self, layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace each parallax band's `image_id` with the asset itself.

        The layout stores an id because that is what the merchant picked; the
        storefront needs URLs and derivatives. Resolved here in one query rather
        than by the client fetching each asset, which would be a round trip per
        band on the page a visitor sees first.
        """
        from apps.media.models import MediaAsset
        from apps.media.serializers import MediaAssetSerializer

        ids = [
            section["image_id"]
            for section in layout
            if section.get("image_id") and str(section.get("key", "")).startswith("parallax:")
        ]
        if not ids:
            return layout

        assets = {
            str(asset.pk): MediaAssetSerializer(asset).data
            for asset in MediaAsset.objects.filter(pk__in=ids, tenant_id=self.tenant_id)
        }

        return [
            {**section, "image": assets.get(str(section.get("image_id")))}
            if str(section.get("key", "")).startswith("parallax:")
            else section
            for section in layout
        ]

    def _layout(self) -> list[dict[str, Any]]:
        """The tenant's layout, falling back to the shipped default.

        A tenant row predating this setting has no layout stored, and a shop
        should never lose its home page to a missing key.
        """
        from apps.tenants.models import default_home_layout

        settings_row = getattr(self.tenant, "settings", None)
        stored = getattr(settings_row, "home_layout", None)

        return stored if isinstance(stored, list) and stored else default_home_layout()


class SearchSuggestionView(TenantScopedMixin, APIView):
    """Autocomplete for the search box."""

    permission_classes = [AllowAny]
    throttle_scope = "search"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, required=True)],
        responses={200: dict},
        operation_id="catalog_search_suggestions",
    )
    def get(self, request: Request) -> Response:
        term = request.query_params.get("q", "")
        suggestions = search_suggestions(storefront_products(self.tenant_id), term)
        return Response({"query": term, "suggestions": suggestions})


class BarcodeLookupView(TenantScopedMixin, APIView):
    """Resolve a scanned barcode to a product."""

    permission_classes = [AllowAny]

    @extend_schema(responses=ProductDetailSerializer, operation_id="catalog_barcode_lookup")
    def get(self, request: Request, code: str) -> Response:
        product = product_by_barcode(self.tenant_id, code)
        if product is None:
            raise NotFoundError()
        context = {
            "request": request,
            "favorite_ids": favorite_product_ids(request.user, self.tenant_id),
        }
        return Response(ProductDetailSerializer(product, context=context).data)


class CategoryViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Public category tree."""

    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self) -> Any:
        return Category.objects.for_tenant(self.tenant_id).filter(is_active=True)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        tree = category_tree(self.tenant_id)
        return Response(self.get_serializer(tree, many=True).data)


class BrandViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self) -> Any:
        return Brand.objects.for_tenant(self.tenant_id).filter(is_active=True).order_by("name")


class FavoriteViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """A customer's saved products."""

    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self) -> Any:
        # The schema generator instantiates the view without a real request, so
        # filtering by `request.user` raises on an AnonymousUser and the model
        # cannot be derived. An empty set is enough for introspection.
        if getattr(self, "swagger_fake_view", False):
            return Favorite.objects.none()

        return (
            Favorite.objects.filter(customer=self.request.user, tenant_id=self.tenant_id)
            .select_related("product", "product__sale_unit", "product__brand")
            .prefetch_related("product__images__asset")
            .order_by("-created_at")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["favorite_ids"] = favorite_product_ids(self.request.user, self.tenant_id)
        return context

    @extend_schema(
        request=FavoriteWriteSerializer,
        responses={201: FavoriteSerializer, 204: None},
        operation_id="favorites_toggle",
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle: posting an existing favourite removes it.

        One endpoint for the heart button, so the client does not have to track
        which state it is in.
        """
        serializer = FavoriteWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = Product.objects.filter(
            tenant_id=self.tenant_id, pk=serializer.validated_data["product"]
        ).first()
        if product is None:
            raise NotFoundError()

        favorite, created = toggle_favorite(customer=request.user, product=product)
        if not created:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            FavoriteSerializer(favorite, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# Merchant administration
# =============================================================================
#: Generous for a catalogue, small enough that a mis-picked file (a photo, a
#: database dump) is refused before it is parsed.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _flag(value: Any) -> bool:
    """Read a checkbox sent through multipart, where everything is a string."""
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


class AdminProductViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Full product management."""

    serializer_class = ProductAdminSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "create": ["catalog.create"],
        "update": ["catalog.update"],
        "partial_update": ["catalog.update"],
        "destroy": ["catalog.delete"],
        "default": ["catalog.update"],
    }
    filterset_fields = ["status", "category", "brand", "is_active", "is_featured"]
    search_fields = ["name", "sku"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    # --- Spreadsheets --------------------------------------------------------

    @extend_schema(
        parameters=[OpenApiParameter("fmt", str, description="csv or xlsx")],
        responses={200: OpenApiTypes.BINARY},
        operation_id="admin_products_export",
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request: Request) -> HttpResponse:
        """The catalogue as a file, in the format the shop's software reads."""
        from .importexport import PRODUCT_COLUMNS, export_products

        return spreadsheets.download(
            columns=PRODUCT_COLUMNS,
            rows=export_products(self.tenant),
            stem="produtos",
            fmt=request.query_params.get("fmt", spreadsheets.XLSX),
        )

    @extend_schema(
        parameters=[OpenApiParameter("fmt", str, description="csv or xlsx")],
        responses={200: OpenApiTypes.BINARY},
        operation_id="admin_products_import_template",
    )
    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request: Request) -> HttpResponse:
        """An empty sheet with the headings, and one example row.

        A merchant who has never seen this format needs to know what goes in
        "Unidade" before they fill in four hundred lines, not after.
        """
        from .importexport import PRODUCT_COLUMNS

        return spreadsheets.download(
            columns=PRODUCT_COLUMNS,
            rows=[{column.key: column.example for column in PRODUCT_COLUMNS}],
            stem="modelo-produtos",
            fmt=request.query_params.get("fmt", spreadsheets.XLSX),
        )

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "dry_run": {"type": "boolean"},
                    "create_missing": {"type": "boolean"},
                },
            }
        },
        responses={200: OpenApiTypes.OBJECT},
        operation_id="admin_products_import",
    )
    @action(detail=False, methods=["post"], url_path="import")
    def import_sheet(self, request: Request) -> Response:
        """Create or update products from an uploaded spreadsheet.

        Answers 200 whether or not the rows were accepted: a sheet with three
        bad lines out of four hundred is a *result* the merchant needs to read
        and act on, not a failed request. `ok` in the body says which it was.
        """
        from .importexport import PRODUCT_COLUMNS, import_products

        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": _("Send a CSV or XLSX file.")})

        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError({"file": _("The file is too large (limit 5 MB).")})

        rows = spreadsheets.parse(
            content=upload.read(), filename=upload.name or "", columns=PRODUCT_COLUMNS
        )
        if not rows:
            raise ValidationError({"file": _("No rows found. Is the first line the headings?")})

        report = import_products(
            tenant=self.tenant,
            rows=rows,
            actor=request.user,
            dry_run=_flag(request.data.get("dry_run")),
            create_missing=_flag(request.data.get("create_missing")),
        )

        if report.ok and not report.dry_run:
            record_audit(
                action="catalog.products_imported",
                tenant=self.tenant,
                actor=request.user,
                new_values={"created": report.created, "updated": report.updated},
                request=request,
            )

        return Response(report.as_dict())

    def get_queryset(self) -> Any:
        queryset = admin_products(self.tenant_id)
        term = self.request.query_params.get("q")
        if term:
            queryset = search_products(queryset, term)
        return apply_sort(queryset, self.request.query_params.get("sort", "name"))

    @extend_schema(
        request=ProductCreateSerializer,
        responses={201: ProductAdminSerializer},
        operation_id="admin_products_create",
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        category = Category.objects.filter(
            tenant_id=self.tenant_id, pk=data.pop("category")
        ).first()
        unit = UnitOfMeasure.objects.filter(
            tenant_id=self.tenant_id, pk=data.pop("sale_unit")
        ).first()
        if category is None or unit is None:
            raise NotFoundError(details={"field": "category or sale_unit"})

        brand_id = data.pop("brand", None)
        base_price = data.pop("base_price", None)
        cost_price = data.pop("cost_price", None)
        initial_stock = data.pop("initial_stock", None)

        product = create_product(
            tenant=self.tenant,
            category=category,
            sale_unit=unit,
            actor=request.user,
            brand_id=brand_id,
            **data,
        )

        if base_price is not None:
            from apps.pricing.services import set_price

            set_price(
                tenant=self.tenant,
                product=product,
                base_price=base_price,
                cost_price=cost_price,
                actor=request.user,
            )

        if initial_stock:
            from apps.inventory.services import set_stock

            set_stock(
                product=product,
                quantity=initial_stock,
                actor=request.user,
                note="Initial stock",
            )

        return Response(
            ProductAdminSerializer(
                admin_products(self.tenant_id).get(pk=product.pk), context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer: Any) -> None:
        product = serializer.instance
        if "name" in serializer.validated_data and not product.slug:
            serializer.validated_data["slug"] = unique_slug(
                Product, self.tenant_id, serializer.validated_data["name"], exclude_pk=product.pk
            )
        serializer.save()

    def perform_destroy(self, instance: Product) -> None:
        """Archive instead of deleting: order history references products."""
        archive_product(instance, actor=self.request.user)

    @extend_schema(
        request=None, responses=ProductAdminSerializer, operation_id="admin_products_publish"
    )
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        product = publish_product(self.get_object(), actor=request.user)
        return Response(ProductAdminSerializer(product).data)

    @extend_schema(
        request=ImageAttachSerializer,
        responses={201: ProductImageSerializer},
        operation_id="admin_products_add_image",
    )
    @action(detail=True, methods=["post"], url_path="images")
    def add_image(self, request: Request, pk: str | None = None) -> Response:
        serializer = ImageAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = attach_image(product=self.get_object(), **serializer.validated_data)
        return Response(ProductImageSerializer(image).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: dict}, operation_id="admin_products_sort_images")
    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request: Request, pk: str | None = None) -> Response:
        reorder_images(self.get_object(), request.data.get("order") or [])
        return Response({"detail": "reordered"})


class AdminCategoryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["catalog.view"], "default": ["catalog.update"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return (
            Category.objects.for_tenant(self.tenant_id)
            .select_related("image")
            .prefetch_related("children", "translations")
            .order_by("position", "name")
        )

    def perform_create(self, serializer: Any) -> None:
        serializer.save(
            tenant=self.tenant,
            slug=unique_slug(Category, self.tenant_id, serializer.validated_data["name"]),
        )


class AdminBrandViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["catalog.view"], "default": ["catalog.update"]}

    def get_queryset(self) -> Any:
        return Brand.objects.for_tenant(self.tenant_id).order_by("name")

    def perform_create(self, serializer: Any) -> None:
        serializer.save(
            tenant=self.tenant,
            slug=unique_slug(Brand, self.tenant_id, serializer.validated_data["name"]),
        )


class AdminTagViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = ProductTagSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["catalog.view"], "default": ["catalog.update"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return ProductTag.objects.for_tenant(self.tenant_id).order_by("name")

    def perform_create(self, serializer: Any) -> None:
        serializer.save(
            tenant=self.tenant,
            slug=unique_slug(ProductTag, self.tenant_id, serializer.validated_data["name"]),
        )


class UnitOfMeasureViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["catalog.view"], "default": ["catalog.update"]}
    pagination_class = None

    def get_queryset(self) -> Any:
        return UnitOfMeasure.objects.for_tenant(self.tenant_id).order_by("name")
