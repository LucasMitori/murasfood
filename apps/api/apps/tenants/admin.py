"""Django admin registrations.

The Django admin is an emergency back-office tool for platform operators. The
merchant-facing dashboard is the Nuxt application (spec §1).
"""

from django.contrib import admin

from .models import BusinessHours, Tenant, TenantBranding, TenantSettings


class TenantBrandingInline(admin.StackedInline):
    model = TenantBranding
    extra = 0
    can_delete = False


class TenantSettingsInline(admin.StackedInline):
    model = TenantSettings
    extra = 0
    can_delete = False


class BusinessHoursInline(admin.TabularInline):
    model = BusinessHours
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("trade_name", "slug", "status", "is_active", "city", "created_at")
    list_filter = ("status", "is_active", "country")
    search_fields = ("trade_name", "legal_name", "slug", "support_email", "tax_id")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (TenantBrandingInline, TenantSettingsInline, BusinessHoursInline)
