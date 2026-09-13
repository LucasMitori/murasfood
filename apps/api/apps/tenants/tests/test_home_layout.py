"""
The home page's layout.

Free-form JSON in the database, so the serializer is the only thing between a
typo and a home page that silently loses a section. These tests are mostly
about what must be *refused* — and about the endpoint honouring what is stored,
because a setting nothing reads is the same as no setting at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.tenants.models import HOME_SECTION_KEYS, TenantSettings

pytestmark = pytest.mark.django_db


def layout(**overrides: Any) -> list[dict[str, Any]]:
    """A valid layout, adjusted per section by keyword."""
    return [
        {"key": key, "enabled": True, "title": "", "limit": 12, **overrides.get(key, {})}
        for key in HOME_SECTION_KEYS
    ]


class TestDefaults:
    def test_every_section_is_on_by_default(self, tenant: Any) -> None:
        settings = TenantSettings.objects.get(tenant=tenant)

        assert [s["key"] for s in settings.home_layout] == list(HOME_SECTION_KEYS)
        assert all(section["enabled"] for section in settings.home_layout)

    def test_two_tenants_do_not_share_one_default(self, tenant: Any, other_tenant: Any) -> None:
        """The mutable-default trap, as with the floating tools."""
        first = TenantSettings.objects.get(tenant=tenant)
        first.home_layout[0]["enabled"] = False
        first.save(update_fields=["home_layout"])

        second = TenantSettings.objects.get(tenant=other_tenant)
        assert second.home_layout[0]["enabled"] is True


class TestValidation:
    ENDPOINT = "/api/v1/tenants/admin/settings/"

    def test_a_valid_layout_is_accepted(self, admin_client_api: Any) -> None:
        response = admin_client_api.patch(
            self.ENDPOINT, {"home_layout": layout(on_sale={"enabled": False})}, format="json"
        )

        assert response.status_code == 200
        stored = {s["key"]: s for s in response.json()["home_layout"]}
        assert stored["on_sale"]["enabled"] is False

    def test_order_is_preserved_exactly(self, admin_client_api: Any) -> None:
        """Order is the whole point: it is the order the rails render in."""
        reversed_layout = list(reversed(layout()))

        response = admin_client_api.patch(
            self.ENDPOINT, {"home_layout": reversed_layout}, format="json"
        )

        assert response.status_code == 200
        keys = [s["key"] for s in response.json()["home_layout"]]
        assert keys == list(reversed(HOME_SECTION_KEYS))

    def test_an_unknown_section_is_refused(self, admin_client_api: Any) -> None:
        broken = [*layout(), {"key": "not_a_section", "enabled": True, "limit": 4}]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": broken}, format="json")

        assert response.status_code == 400

    def test_a_repeated_section_is_refused(self, admin_client_api: Any) -> None:
        """De-duplicating silently would render the same rail twice."""
        broken = [*layout(), {"key": "featured", "enabled": True, "limit": 4}]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": broken}, format="json")

        assert response.status_code == 400

    def test_a_missing_section_is_refused(self, admin_client_api: Any) -> None:
        """Dropping a key would remove the rail with no way to bring it back."""
        broken = [s for s in layout() if s["key"] != "featured"]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": broken}, format="json")

        assert response.status_code == 400

    @pytest.mark.parametrize("limit", [0, -1, 25, "many"])
    def test_an_impossible_limit_is_refused(self, admin_client_api: Any, limit: Any) -> None:
        response = admin_client_api.patch(
            self.ENDPOINT, {"home_layout": layout(featured={"limit": limit})}, format="json"
        )

        assert response.status_code == 400


class TestTheStorefrontHonoursIt:
    def test_a_disabled_section_is_not_sent(
        self, api_client: Any, admin_client_api: Any, product_factory: Any
    ) -> None:
        product_factory(name="Featured One", is_featured=True)
        admin_client_api.patch(
            "/api/v1/tenants/admin/settings/",
            {"home_layout": layout(featured={"enabled": False})},
            format="json",
        )

        body = api_client.get("/api/v1/catalog/home/").json()

        assert body["featured"] == []
        # The rail is still described, so the dashboard can show it as off
        # rather than as missing.
        assert [s["key"] for s in body["layout"]] == list(HOME_SECTION_KEYS)

    def test_the_limit_caps_a_rail(
        self, api_client: Any, admin_client_api: Any, product_factory: Any
    ) -> None:
        for index in range(5):
            product_factory(name=f"New {index}")

        admin_client_api.patch(
            "/api/v1/tenants/admin/settings/",
            {"home_layout": layout(new_arrivals={"limit": 2})},
            format="json",
        )

        body = api_client.get("/api/v1/catalog/home/").json()

        assert len(body["new_arrivals"]) == 2

    def test_the_order_reaches_the_storefront(self, api_client: Any, admin_client_api: Any) -> None:
        admin_client_api.patch(
            "/api/v1/tenants/admin/settings/",
            {"home_layout": list(reversed(layout()))},
            format="json",
        )

        body = api_client.get("/api/v1/catalog/home/").json()

        assert [s["key"] for s in body["layout"]] == list(reversed(HOME_SECTION_KEYS))


class TestTheDashboardCanReadItBack:
    """The layout editor reads the tenant through the *public* serializer.

    That serializer has its own explicit allow-list, so a field added to the
    model reaches it only if someone remembers. Forgetting leaves the editor
    permanently showing the default order however many times the merchant saves
    — the same failure the floating-button screen already had once.
    """

    def test_the_public_tenant_carries_the_layout(
        self, api_client: Any, admin_client_api: Any
    ) -> None:
        admin_client_api.patch(
            "/api/v1/tenants/admin/settings/",
            {"home_layout": layout(featured={"enabled": False, "title": "Nossa seleção"})},
            format="json",
        )

        settings = api_client.get("/api/v1/tenants/current/").json()["settings"]

        stored = {s["key"]: s for s in settings["home_layout"]}
        assert stored["featured"]["enabled"] is False
        assert stored["featured"]["title"] == "Nossa seleção"


def band(key: str = "parallax:a", **overrides: Any) -> dict[str, Any]:
    """One merchant-authored parallax band."""
    return {
        "key": key,
        "enabled": True,
        "title": "Feira fresca",
        "subtitle": "Todo dia, do produtor para a sua mesa",
        "cta_label": "Ver ofertas",
        "cta_url": "/products",
        "image_id": None,
        "height": 70,
        "overlay": 45,
        "align": "center",
        **overrides,
    }


class TestParallaxBands:
    """Bands share the rails' list, because the order is the page.

    Two lists interleaved by a position field would be the same information
    stated in a way that can disagree with itself.
    """

    ENDPOINT = "/api/v1/tenants/admin/settings/"

    def test_a_band_can_be_placed_between_rails(self, admin_client_api: Any) -> None:
        sections = layout()
        sections.insert(1, band())

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        assert response.status_code == 200, response.json()
        keys = [s["key"] for s in response.json()["home_layout"]]
        assert keys[1] == "parallax:a"
        assert len(keys) == len(HOME_SECTION_KEYS) + 1

    def test_a_shop_may_have_no_bands_at_all(self, admin_client_api: Any) -> None:
        """The switch is the feature: a short page must stay possible."""
        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": layout()}, format="json")

        assert response.status_code == 200
        assert not any(s["key"].startswith("parallax:") for s in response.json()["home_layout"])

    def test_the_rails_are_still_all_required(self, admin_client_api: Any) -> None:
        """Adding bands must not weaken the rule that protects the rails."""
        broken = [s for s in layout() if s["key"] != "featured"] + [band()]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": broken}, format="json")

        assert response.status_code == 400

    def test_too_many_bands_are_refused(self, admin_client_api: Any) -> None:
        """A page is a shop, not a brochure."""
        sections = [*layout(), *(band(f"parallax:{i}") for i in range(8))]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        assert response.status_code == 400

    @pytest.mark.parametrize("height", [0, 50, 120, "tall"])
    def test_an_unsupported_height_is_refused(self, admin_client_api: Any, height: Any) -> None:
        sections = [*layout(), band(height=height)]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "url", ["javascript:alert(1)", "data:text/html,<script>", "vbscript:x"]
    )
    def test_a_scripted_link_is_refused(self, admin_client_api: Any, url: str) -> None:
        """The merchant writes this, and their own customers click it. A stored
        `javascript:` URL is XSS against the people they are selling to."""
        sections = [*layout(), band(cta_url=url)]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        assert response.status_code == 400

    @pytest.mark.parametrize("url", ["/products", "https://exemplo.com.br", ""])
    def test_ordinary_links_are_accepted(self, admin_client_api: Any, url: str) -> None:
        sections = [*layout(), band(cta_url=url)]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        assert response.status_code == 200, response.json()

    def test_a_disabled_band_survives_the_round_trip(self, admin_client_api: Any) -> None:
        """Switched off is not deleted: the merchant gets their copy back when
        they switch it on again."""
        sections = [*layout(), band(enabled=False, title="Guardado")]

        response = admin_client_api.patch(self.ENDPOINT, {"home_layout": sections}, format="json")

        stored = next(s for s in response.json()["home_layout"] if s["key"] == "parallax:a")
        assert stored["enabled"] is False
        assert stored["title"] == "Guardado"


class TestHero:
    ENDPOINT = "/api/v1/tenants/admin/settings/"

    def test_parallax_is_off_by_default(self, tenant: Any) -> None:
        """Turning it on for everyone would change every existing storefront on
        the day this deploys."""
        settings = TenantSettings.objects.get(tenant=tenant)

        assert settings.hero["parallax"] is False

    def test_it_can_be_switched_on(self, admin_client_api: Any) -> None:
        response = admin_client_api.patch(
            self.ENDPOINT,
            {"hero": {"parallax": True, "full_height": True, "overlay": 60}},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["hero"] == {
            "parallax": True,
            "full_height": True,
            "overlay": 60,
        }

    def test_an_impossible_overlay_is_refused(self, admin_client_api: Any) -> None:
        response = admin_client_api.patch(self.ENDPOINT, {"hero": {"overlay": 200}}, format="json")

        assert response.status_code == 400

    def test_the_storefront_can_read_it(self, api_client: Any, admin_client_api: Any) -> None:
        """The public serializer keeps its own allow-list — this has been
        forgotten twice before, with floating_tools and home_layout."""
        admin_client_api.patch(
            self.ENDPOINT, {"hero": {"parallax": True, "full_height": True}}, format="json"
        )

        settings = api_client.get("/api/v1/tenants/current/").json()["settings"]

        assert settings["hero"]["parallax"] is True
