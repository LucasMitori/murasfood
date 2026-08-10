from django.contrib import admin

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


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    autocomplete_fields = ("asset",)


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 0


class ProductTranslationInline(admin.TabularInline):
    model = ProductTranslation
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "status", "is_active", "tenant")
    list_filter = ("status", "is_active", "is_featured", "tenant", "category")
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category", "brand", "sale_unit")
    inlines = (ProductImageInline, ProductBarcodeInline, ProductTranslationInline)
    readonly_fields = ("sales_count", "view_count", "created_at", "updated_at")


class CategoryTranslationInline(admin.TabularInline):
    model = CategoryTranslation
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "position", "is_active", "tenant")
    list_filter = ("is_active", "tenant")
    search_fields = ("name", "slug")
    inlines = (CategoryTranslationInline,)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "tenant")
    search_fields = ("name", "slug")


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "precision", "step", "tenant")
    search_fields = ("code", "name")


@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant")
    search_fields = ("name", "slug")


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("customer", "product", "created_at")
    search_fields = ("customer__email", "product__name")
