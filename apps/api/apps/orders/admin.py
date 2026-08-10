from django.contrib import admin

from .models import Order, OrderAddress, OrderItem, OrderNote, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = tuple(f.name for f in OrderItem._meta.fields)
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = tuple(f.name for f in OrderStatusHistory._meta.fields)
    can_delete = False


class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Read-mostly. Status changes belong to the API's state machine."""

    list_display = ("number", "customer_name", "status", "total", "delivery_method", "created_at")
    list_filter = ("status", "delivery_method", "tenant")
    search_fields = ("number", "customer_name", "customer_email", "customer_phone")
    date_hierarchy = "created_at"
    inlines = (OrderItemInline, OrderAddressInline, OrderStatusHistoryInline)
    readonly_fields = (
        "number",
        "subtotal",
        "discount_total",
        "delivery_fee",
        "tax_total",
        "total",
        "refunded_total",
        "placed_at",
        "paid_at",
        "completed_at",
    )

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(OrderNote)
class OrderNoteAdmin(admin.ModelAdmin):
    list_display = ("order", "author", "is_customer_visible", "created_at")
    search_fields = ("order__number", "body")
