"""Notification serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import EmailLog, EmailTemplate, Notification


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            "id",
            "key",
            "locale",
            "subject",
            "html_body",
            "text_body",
            "available_variables",
            "version",
            "is_active",
            "updated_at",
        ]
        read_only_fields = ["id", "version", "updated_at"]

    def validate_html_body(self, value: str) -> str:
        """Reject anything that would execute in a mail client.

        Templates are merchant-editable; a ``<script>`` tag in a transactional
        email is both a security problem and a spam-filter magnet.
        """
        lowered = value.lower()
        for forbidden in ("<script", "javascript:", "onerror=", "onload="):
            if forbidden in lowered:
                raise serializers.ValidationError(
                    "Scripts and inline event handlers are not allowed in email templates."
                )
        return value


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = [
            "id",
            "template_key",
            "recipient",
            "subject",
            "status",
            "attempts",
            "last_error",
            "related_type",
            "related_id",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "channel",
            "notification_type",
            "title",
            "body",
            "payload",
            "status",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
