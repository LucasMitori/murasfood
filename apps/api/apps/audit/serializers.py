from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "actor",
            "actor_label",
            "resource_type",
            "resource_id",
            "old_values",
            "new_values",
            "ip_address",
            "request_id",
            "created_at",
        ]
        read_only_fields = fields
