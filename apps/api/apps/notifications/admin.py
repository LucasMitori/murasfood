from django.contrib import admin

from .models import EmailLog, EmailTemplate, Notification


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("key", "locale", "subject", "is_active", "version", "tenant")
    list_filter = ("locale", "is_active", "tenant")
    search_fields = ("key", "subject")


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "template_key", "recipient", "status", "attempts")
    list_filter = ("status", "template_key", "tenant")
    search_fields = ("recipient", "subject", "related_id")
    readonly_fields = tuple(f.name for f in EmailLog._meta.fields)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "notification_type", "title", "status")
    list_filter = ("channel", "status", "tenant")
    search_fields = ("title", "user__email")
