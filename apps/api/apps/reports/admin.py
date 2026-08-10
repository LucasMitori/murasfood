from django.contrib import admin

from .models import ReportJob


@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = ("report_type", "status", "requested_by", "created_at", "completed_at")
    list_filter = ("report_type", "status", "tenant")
    readonly_fields = ("parameters", "error_message", "started_at", "completed_at")
