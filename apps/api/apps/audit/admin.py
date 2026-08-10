from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Strictly read-only, including for superusers."""

    list_display = ("created_at", "action", "actor_label", "resource_type", "resource_id", "tenant")
    list_filter = ("action", "resource_type", "tenant")
    search_fields = ("action", "actor_label", "resource_id", "request_id")
    date_hierarchy = "created_at"
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
