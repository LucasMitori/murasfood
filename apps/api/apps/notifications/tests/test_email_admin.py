"""
Managing email from the dashboard.

Three things must hold: a preview must never need real customer data, a test
send must report a broken connection rather than raising, and the SMTP password
must never leave the server.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core import mail

from apps.notifications.models import EmailTemplate
from apps.notifications.services import connection_for
from apps.tenants.models import TenantSettings

pytestmark = pytest.mark.django_db


def a_template(tenant: Any) -> EmailTemplate:
    return EmailTemplate.objects.filter(tenant=tenant, key="account.verify").first()


class TestPreview:
    def test_placeholders_are_filled_with_samples(self, admin_client: Any, tenant: Any) -> None:
        """The point is to see the message, not the source."""
        template = a_template(tenant)

        body = admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/preview/",
            {},
            content_type="application/json",
        ).json()

        assert "{{" not in body["html"]
        assert "{{" not in body["subject"]
        assert "Maria" in body["html"]

    def test_supplied_values_win_over_samples(self, admin_client: Any, tenant: Any) -> None:
        template = a_template(tenant)

        body = admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/preview/",
            {"context": {"first_name": "Joana"}},
            content_type="application/json",
        ).json()

        assert "Joana" in body["html"]
        assert "Maria" not in body["html"]

    def test_preview_sends_nothing(self, admin_client: Any, tenant: Any) -> None:
        """Looking at a template must not put mail in anyone's inbox."""
        template = a_template(tenant)
        before = len(mail.outbox)

        admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/preview/",
            {},
            content_type="application/json",
        )

        assert len(mail.outbox) == before


class TestTestSend:
    def test_a_test_actually_sends(self, admin_client: Any, tenant: Any) -> None:
        template = a_template(tenant)

        response = admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/test/",
            {"recipient": "operator@example.test"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["sent"] is True
        assert mail.outbox[-1].to == ["operator@example.test"]

    def test_it_is_marked_as_a_test(self, admin_client: Any, tenant: Any) -> None:
        """So nobody mistakes one for a real order confirmation."""
        template = a_template(tenant)
        admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/test/",
            {"recipient": "operator@example.test"},
            content_type="application/json",
        )

        assert mail.outbox[-1].subject.startswith("[teste]")

    def test_a_missing_address_is_refused(self, admin_client: Any, tenant: Any) -> None:
        template = a_template(tenant)

        response = admin_client.post(
            f"/api/v1/admin/email-templates/{template.pk}/test/",
            {},
            content_type="application/json",
        )

        assert response.status_code == 400


class TestTenantConnection:
    def test_no_host_means_the_platform_server(self, tenant: Any) -> None:
        """A merchant who has configured nothing must still get mail sent."""
        assert connection_for(tenant) is None

    def test_a_half_filled_form_falls_back_rather_than_breaking(self, tenant: Any) -> None:
        """A username with no host is a form in progress, not a configuration."""
        row = TenantSettings.objects.get(tenant=tenant)
        row.smtp_username = "someone"
        row.save(update_fields=["smtp_username"])
        tenant.refresh_from_db()
        tenant._state.fields_cache.pop("settings", None)

        assert connection_for(tenant) is None

    def test_a_host_produces_a_connection_using_it(self, tenant: Any) -> None:
        row = TenantSettings.objects.get(tenant=tenant)
        row.smtp_host = "smtp.merchant.test"
        row.smtp_port = 2525
        row.save(update_fields=["smtp_host", "smtp_port"])

        # `tenant.settings` is a cached relation; without clearing it the
        # connection would be built from the values loaded before the save.
        tenant.refresh_from_db()
        tenant._state.fields_cache.pop("settings", None)

        connection = connection_for(tenant)

        assert connection is not None
        assert connection.host == "smtp.merchant.test"
        assert connection.port == 2525


class TestPasswordSecrecy:
    def test_the_password_is_never_returned(self, admin_client: Any, tenant: Any) -> None:
        """A password the API hands back is one in every cache that saw it."""
        # The endpoint only accepts PATCH, so its own response is the read.
        body = admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"smtp_host": "smtp.merchant.test", "smtp_password": "hunter2"},
            content_type="application/json",
        ).json()

        assert "smtp_password" not in body
        assert body["smtp_password_set"] is True
        assert "hunter2" not in str(body)

    def test_editing_another_field_keeps_the_password(
        self, admin_client: Any, tenant: Any
    ) -> None:
        """The form cannot send back a secret it was never given."""
        admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"smtp_password": "hunter2"},
            content_type="application/json",
        )

        admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"smtp_host": "smtp.elsewhere.test"},
            content_type="application/json",
        )

        assert TenantSettings.objects.get(tenant=tenant).smtp_password == "hunter2"

    def test_an_explicit_empty_string_clears_it(self, admin_client: Any, tenant: Any) -> None:
        admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"smtp_password": "hunter2"},
            content_type="application/json",
        )

        admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"smtp_password": ""},
            content_type="application/json",
        )

        assert TenantSettings.objects.get(tenant=tenant).smtp_password == ""
