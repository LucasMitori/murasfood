"""
Two things the product editor gained: per-product stock thresholds, and a
gallery with an order and captions.

The thresholds matter because one shared "low stock" number cannot be right for
both a sack of rice and forty litres of milk — which is why the stock-health
screen was either noisy or silent. The gallery matters because order decides
which photo represents the product everywhere else in the shop.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.catalog.models import ProductImage
from apps.inventory.models import InventoryItem

pytestmark = pytest.mark.django_db


def endpoint(product: Any) -> str:
    return f"/api/v1/admin/products/{product.pk}/"


class TestStockThresholds:
    def test_they_can_be_set_from_the_product_form(
        self, admin_client_api: Any, product: Any
    ) -> None:
        response = admin_client_api.patch(
            endpoint(product),
            {"low_stock_threshold": "12.000", "minimum_stock": "5.000"},
            format="json",
        )

        assert response.status_code == 200
        item = InventoryItem.objects.get(product=product)
        assert item.reorder_threshold == Decimal("12.000")
        assert item.minimum_stock == Decimal("5.000")

    def test_the_response_echoes_what_was_just_saved(
        self, admin_client_api: Any, product: Any
    ) -> None:
        """A form that cannot read back its own save is a form people stop
        trusting — and this returned the *pre-save* values, because
        `get_or_create_item` hands back a different object from the one the
        product's relation cache is holding.
        """
        response = admin_client_api.patch(
            endpoint(product),
            {"low_stock_threshold": "20.000", "minimum_stock": "8.000"},
            format="json",
        )

        assert response.json()["low_stock_threshold"] == "20.000"
        assert response.json()["minimum_stock"] == "8.000"

    def test_they_survive_a_reload(self, admin_client_api: Any, product: Any) -> None:
        admin_client_api.patch(
            endpoint(product), {"low_stock_threshold": "7.000"}, format="json"
        )

        body = admin_client_api.get(endpoint(product)).json()

        assert body["low_stock_threshold"] == "7.000"

    def test_setting_a_threshold_does_not_move_stock(
        self, admin_client_api: Any, product: Any
    ) -> None:
        """A rule *about* the stock is not a change *to* it. Routing these
        through `adjust_stock` would write a movement row saying nothing moved.
        """
        from apps.inventory.models import StockMovement

        before = StockMovement.objects.filter(product=product).count()
        quantity = InventoryItem.objects.get(product=product).quantity

        admin_client_api.patch(
            endpoint(product), {"low_stock_threshold": "9.000"}, format="json"
        )

        assert StockMovement.objects.filter(product=product).count() == before
        assert InventoryItem.objects.get(product=product).quantity == quantity

    def test_tracking_can_be_turned_off(self, admin_client_api: Any, product: Any) -> None:
        """For made-to-order items — the day's bread is never "out of stock"."""
        admin_client_api.patch(endpoint(product), {"track_stock": False}, format="json")

        assert InventoryItem.objects.get(product=product).track_stock is False

    def test_the_threshold_drives_the_low_stock_flag(
        self, admin_client_api: Any, product: Any
    ) -> None:
        """The point of the whole field: it has to change what the stock screens
        say, or it is a number in a box."""
        from apps.inventory.services import set_stock

        set_stock(product=product, quantity=Decimal("10"))

        admin_client_api.patch(
            endpoint(product), {"low_stock_threshold": "3.000"}, format="json"
        )
        assert InventoryItem.objects.get(product=product).is_low_stock is False

        admin_client_api.patch(
            endpoint(product), {"low_stock_threshold": "15.000"}, format="json"
        )
        assert InventoryItem.objects.get(product=product).is_low_stock is True


class TestGallery:
    @pytest.fixture
    def asset(self, tenant: Any) -> Any:
        from apps.media.models import MediaAsset

        return MediaAsset.objects.create(
            tenant=tenant,
            storage_key=f"{tenant.pk}/products/gallery-test.webp",
            original_filename="gallery-test.webp",
            content_type="image/webp",
        )

    def test_order_and_captions_are_stored(
        self, admin_client_api: Any, product: Any, asset: Any, tenant: Any
    ) -> None:
        from apps.media.models import MediaAsset

        second = MediaAsset.objects.create(
            tenant=tenant,
            storage_key=f"{tenant.pk}/products/gallery-two.webp",
            original_filename="gallery-two.webp",
            content_type="image/webp",
        )

        response = admin_client_api.patch(
            endpoint(product),
            {
                "gallery": [
                    {"id": str(second.pk), "caption": "Rótulo"},
                    {"id": str(asset.pk), "caption": "Porção servida"},
                ]
            },
            format="json",
        )

        assert response.status_code == 200
        rows = list(ProductImage.objects.filter(product=product).order_by("position"))
        assert [row.caption for row in rows] == ["Rótulo", "Porção servida"]
        assert [row.asset_id for row in rows] == [second.pk, asset.pk]

    def test_the_first_image_is_the_primary_one(
        self, admin_client_api: Any, product: Any, asset: Any
    ) -> None:
        """Implicit rather than a separate flag: two ways to say the same thing
        eventually disagree."""
        admin_client_api.patch(
            endpoint(product), {"gallery": [{"id": str(asset.pk)}]}, format="json"
        )

        row = ProductImage.objects.get(product=product)
        assert row.is_primary is True
        assert row.position == 0

    def test_an_unknown_image_is_refused_rather_than_dropped(
        self, admin_client_api: Any, product: Any, asset: Any
    ) -> None:
        """The first version filtered silently, which turned one bad id into
        "all my photos vanished"."""
        admin_client_api.patch(
            endpoint(product), {"gallery": [{"id": str(asset.pk)}]}, format="json"
        )

        response = admin_client_api.patch(
            endpoint(product),
            {"gallery": [{"id": "00000000-0000-0000-0000-000000000000"}]},
            format="json",
        )

        assert response.status_code == 400
        # And the gallery it would have replaced is still there.
        assert ProductImage.objects.filter(product=product).count() == 1

    def test_another_shops_asset_is_refused(
        self, admin_client_api: Any, product: Any, other_tenant: Any
    ) -> None:
        from apps.media.models import MediaAsset

        foreign = MediaAsset.objects.create(
            tenant=other_tenant,
            storage_key=f"{other_tenant.pk}/products/theirs.webp",
            original_filename="theirs.webp",
            content_type="image/webp",
        )

        response = admin_client_api.patch(
            endpoint(product), {"gallery": [{"id": str(foreign.pk)}]}, format="json"
        )

        assert response.status_code == 400

    def test_an_empty_gallery_clears_the_images(
        self, admin_client_api: Any, product: Any, asset: Any
    ) -> None:
        admin_client_api.patch(
            endpoint(product), {"gallery": [{"id": str(asset.pk)}]}, format="json"
        )

        admin_client_api.patch(endpoint(product), {"gallery": []}, format="json")

        assert ProductImage.objects.filter(product=product).count() == 0

    def test_not_mentioning_the_gallery_leaves_it_alone(
        self, admin_client_api: Any, product: Any, asset: Any
    ) -> None:
        """`None` means "I did not say"; `[]` means "I said none". Only the
        second should clear anything."""
        admin_client_api.patch(
            endpoint(product), {"gallery": [{"id": str(asset.pk)}]}, format="json"
        )

        admin_client_api.patch(endpoint(product), {"name": "Novo nome"}, format="json")

        assert ProductImage.objects.filter(product=product).count() == 1


class TestCategoryCounts:
    def test_a_root_counts_its_subcategories_products(
        self, admin_client_api: Any, tenant: Any, category: Any, product_factory: Any
    ) -> None:
        """Clicking a category in the shop shows its children's products, so a
        root reading 0 while a tap on it lists forty is a number that teaches
        people to distrust the screen.
        """
        from apps.catalog.models import Category

        child = Category.objects.create(
            tenant=tenant, name="Subcategoria", slug="subcategoria", parent=category
        )
        product_factory(name="No filho", category=child)

        body = admin_client_api.get("/api/v1/admin/categories/").json()
        root = next(row for row in body if row["id"] == str(category.pk))

        assert root["product_count"] >= 1
