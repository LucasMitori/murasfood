from django.contrib import admin

from .models import Banner, Document, MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "kind", "folder", "status", "tenant", "created_at")
    list_filter = ("kind", "folder", "status", "tenant")
    search_fields = ("original_filename", "storage_key", "checksum")
    readonly_fields = ("id", "storage_key", "checksum", "size_bytes", "created_at", "updated_at")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "tenant", "created_at")
    list_filter = ("document_type", "tenant")
    search_fields = ("title", "related_id")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "is_active", "priority", "start_at", "end_at")
    list_filter = ("is_active", "link_type", "tenant")
    search_fields = ("title", "subtitle")
