from django.contrib import admin

from .models import Payment, PaymentEvent, PaymentRefund


class PaymentEventInline(admin.TabularInline):
    model = PaymentEvent
    extra = 0
    readonly_fields = tuple(f.name for f in PaymentEvent._meta.fields)
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Read-only. Money never moves from the Django admin."""

    list_display = ("id", "order", "provider", "method", "status", "amount", "paid_at")
    list_filter = ("status", "method", "provider", "tenant")
    search_fields = ("external_id", "pix_transaction_id", "order__number")
    readonly_fields = tuple(f.name for f in Payment._meta.fields)
    inlines = (PaymentEventInline,)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "provider", "event_type", "processing_status", "signature_valid")
    list_filter = ("processing_status", "provider", "signature_valid")
    search_fields = ("provider_event_id", "payload_hash")
    readonly_fields = tuple(f.name for f in PaymentEvent._meta.fields)


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount", "status", "requested_by", "created_at")
    list_filter = ("status", "tenant")
    readonly_fields = tuple(f.name for f in PaymentRefund._meta.fields)
