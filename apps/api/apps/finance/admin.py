from django.contrib import admin

from .models import FinancialAccount, FinancialCategory, FinancialTransaction


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "is_default", "is_active", "tenant")
    list_filter = ("account_type", "is_active", "tenant")


@admin.register(FinancialCategory)
class FinancialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "kind", "is_active", "tenant")
    list_filter = ("kind", "is_active", "tenant")
    search_fields = ("name", "code")


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_on",
        "description",
        "transaction_type",
        "amount",
        "category",
        "status",
    )
    list_filter = ("transaction_type", "status", "category", "tenant")
    search_fields = ("description", "reference_id")
    date_hierarchy = "occurred_on"

    def has_delete_permission(self, request, obj=None) -> bool:
        """Ledger entries are voided through the API, never deleted."""
        return False
