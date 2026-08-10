from django.contrib import admin

from .models import Coupon, CouponRedemption, Promotion


class CouponInline(admin.TabularInline):
    model = Coupon
    extra = 0


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_type", "value", "is_active", "starts_at", "ends_at", "tenant")
    list_filter = ("discount_type", "scope", "is_active", "tenant")
    search_fields = ("name",)
    filter_horizontal = ("products", "categories")
    inlines = (CouponInline,)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "promotion", "used_count", "max_uses", "is_active", "tenant")
    list_filter = ("is_active", "tenant")
    search_fields = ("code",)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "customer", "order", "discount_amount", "created_at")
    search_fields = ("coupon__code",)
    readonly_fields = tuple(f.name for f in CouponRedemption._meta.fields)
