from django.contrib import admin

from .models import PriceHistory, PriceList, ProductPrice


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant", "is_default", "is_active")
    list_filter = ("is_default", "is_active", "tenant")


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "base_price",
        "sale_price",
        "cost_price",
        "min_quantity",
        "is_active",
    )
    list_filter = ("is_active", "tenant")
    search_fields = ("product__name", "product__sku")
    autocomplete_fields = ("product",)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    """Read-only: history rows are immutable."""

    list_display = ("product", "field", "old_value", "new_value", "reason", "created_at")
    list_filter = ("field", "reason", "tenant")
    search_fields = ("product__name", "product__sku")
    readonly_fields = tuple(f.name for f in PriceHistory._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
