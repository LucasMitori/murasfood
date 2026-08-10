"""Report serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import ReportJob


class ReportJobSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()
    is_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = ReportJob
        fields = [
            "id",
            "report_type",
            "output_format",
            "status",
            "parameters",
            "is_ready",
            "download_url",
            "filename",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_download_url(self, obj: ReportJob) -> str | None:
        """Signed, expiring URL. Reports are private documents."""
        if obj.asset is None:
            return None
        from apps.media.services import asset_url

        return asset_url(obj.asset)

    def get_filename(self, obj: ReportJob) -> str | None:
        return obj.asset.original_filename if obj.asset else None


class ReportRequestSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(
        choices=["SALES", "PRODUCTS", "CUSTOMERS", "INVENTORY", "FINANCIAL"]
    )
    period = serializers.CharField(required=False, default="last_30")
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)


class DashboardSerializer(serializers.Serializer):
    """Documents the dashboard payload for OpenAPI consumers."""

    period = serializers.DictField()
    revenue = serializers.DictField()
    orders = serializers.DictField()
    counters = serializers.DictField()
    charts = serializers.DictField()
    customers = serializers.DictField()
    recent_orders = serializers.ListField(child=serializers.DictField())
    alerts = serializers.DictField()

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        return instance
