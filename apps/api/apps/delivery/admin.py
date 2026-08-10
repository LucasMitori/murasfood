from django.contrib import admin

from .models import DeliverySettings, DeliveryZone


@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "delivery_enabled", "pickup_enabled", "base_fee")


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "postal_code_start", "postal_code_end", "fee", "is_active", "tenant")
    list_filter = ("is_active", "tenant")
    search_fields = ("name", "postal_code_start", "postal_code_end")
