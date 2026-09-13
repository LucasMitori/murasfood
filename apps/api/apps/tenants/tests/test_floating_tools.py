"""
The floating button's configuration.

It is free-form JSON in the database, so the serializer is the only thing
standing between a typo and a shortcut that silently vanishes from the
storefront. These tests are about what must be *refused*.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.tenants.models import FLOATING_TOOL_KEYS, TenantSettings

pytestmark = pytest.mark.django_db


class TestDefaults:
    def test_every_tool_is_on_by_default(self, tenant: Any) -> None:
        settings = TenantSettings.objects.get(tenant=tenant)

        assert settings.floating_tools["enabled"] is True
        assert set(settings.floating_tools["actions"]) == set(FLOATING_TOOL_KEYS)

    def test_two_tenants_do_not_share_one_default(self, tenant: Any) -> None:
        """A mutable default is shared by every row that uses it.

        Without a callable, one shop reordering its buttons would reorder
        everyone's. Comparing two freshly built defaults is enough to show they
        are separate objects.
        """
        from apps.tenants.models import default_floating_tools

        mine = default_floating_tools()
        theirs = default_floating_tools()

        mine["actions"].append("calculator")

        assert theirs["actions"].count("calculator") == 1
        assert mine is not theirs


class TestValidation:
    def _patch(self, client: Any, payload: dict) -> Any:
        return client.patch(
            "/api/v1/tenants/admin/settings/",
            {"floating_tools": payload},
            content_type="application/json",
        )

    def test_an_unknown_tool_is_refused(self, admin_client: Any) -> None:
        """Storing it would drop the shortcut silently at render time."""
        response = self._patch(admin_client, {"actions": ["calculator", "teleporter"]})

        assert response.status_code == 400
        assert "floating_tools" in response.json()["error"]["details"]

    def test_a_repeated_tool_is_refused(self, admin_client: Any) -> None:
        """It would render the same button twice."""
        response = self._patch(admin_client, {"actions": ["cart", "cart"]})

        assert response.status_code == 400

    def test_an_unknown_position_is_refused(self, admin_client: Any) -> None:
        response = self._patch(admin_client, {"actions": ["cart"], "position": "middle-of-nowhere"})

        assert response.status_code == 400

    def test_order_is_preserved(self, admin_client: Any, tenant: Any) -> None:
        """The list is the display order, so it must survive a round trip."""
        wanted = ["whatsapp", "calculator", "top"]
        response = self._patch(admin_client, {"actions": wanted})

        assert response.status_code == 200
        assert response.json()["floating_tools"]["actions"] == wanted

    def test_an_empty_list_is_allowed(self, admin_client: Any) -> None:
        """A shop may want the button with nothing but its own tools removed."""
        response = self._patch(admin_client, {"actions": []})

        assert response.status_code == 200
        assert response.json()["floating_tools"]["actions"] == []

    def test_missing_keys_fall_back_rather_than_erroring(self, admin_client: Any) -> None:
        """A partial object is a reasonable thing for a client to send."""
        response = self._patch(admin_client, {"actions": ["cart"]})

        assert response.status_code == 200
        body = response.json()["floating_tools"]
        assert body["position"] == "bottom-right"
        assert body["icon"] == "mdi-apps"


class TestReachesTheStorefront:
    """A setting the storefront cannot read is a setting that does nothing.

    The admin endpoint and the public one use different serializers, so adding
    a field to the first does not add it to the second — and the button would
    quietly keep showing every shortcut no matter what was saved.
    """

    def test_current_tenant_exposes_the_configuration(self, client: Any, tenant: Any) -> None:
        response = client.get("/api/v1/tenants/current/", headers={"X-Tenant": tenant.slug})

        assert response.status_code == 200
        assert "floating_tools" in response.json()["settings"]

    def test_a_saved_choice_is_what_the_storefront_reads(
        self, admin_client: Any, client: Any, tenant: Any
    ) -> None:
        admin_client.patch(
            "/api/v1/tenants/admin/settings/",
            {"floating_tools": {"actions": ["cart", "calculator"], "position": "top-left"}},
            content_type="application/json",
        )

        body = client.get("/api/v1/tenants/current/", headers={"X-Tenant": tenant.slug}).json()[
            "settings"
        ]["floating_tools"]

        assert body["actions"] == ["cart", "calculator"]
        assert body["position"] == "top-left"
