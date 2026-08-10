from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "tenant", "updated_at")
    list_filter = ("status", "tenant")
    search_fields = ("customer__email", "token")
    inlines = (CartItemInline,)
