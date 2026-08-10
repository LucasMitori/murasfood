from django.contrib import admin

from .models import InventoryItem, StockMovement, StockReservation


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("product", "quantity", "reserved_quantity", "track_stock", "tenant")
    list_filter = ("track_stock", "tenant")
    search_fields = ("product__name", "product__sku")
    autocomplete_fields = ("product",)
    readonly_fields = ("quantity", "reserved_quantity")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Read-only: movements are the ledger."""

    list_display = ("created_at", "product", "movement_type", "quantity", "balance_after")
    list_filter = ("movement_type", "tenant")
    search_fields = ("product__name", "product__sku", "reference_id")
    readonly_fields = tuple(f.name for f in StockMovement._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ("product", "quantity", "status", "expires_at", "order")
    list_filter = ("status", "tenant")
    search_fields = ("product__name",)
