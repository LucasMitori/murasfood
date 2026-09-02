"""
Attaching images to a product.

The nested `images` serializer is read-only — a client sends assets it has
already uploaded, not image rows — so `image_ids` is the write side. What
matters here is that the list is authoritative: its order becomes the display
order, its first entry is the primary image, and sending a shorter list removes
what is no longer in it.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.catalog.models import Product, ProductImage

pytestmark = pytest.mark.django_db


def make_asset(tenant: Any, name: str) -> Any:
    from apps.media.models import MediaAsset

    return MediaAsset.objects.create(
        tenant=tenant,
        kind="IMAGE",
        status="READY",
        original_filename=name,
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key=f"test/{name}",
    )


class TestAttachingImages:
    def test_first_asset_becomes_the_primary_image(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        one = make_asset(tenant, "one.jpg")
        two = make_asset(tenant, "two.jpg")

        response = admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": [str(one.pk), str(two.pk)]},
            content_type="application/json",
        )

        assert response.status_code == 200
        rows = list(ProductImage.objects.filter(product=product).order_by("position"))
        assert [row.asset_id for row in rows] == [one.pk, two.pk]
        assert [row.is_primary for row in rows] == [True, False]

    def test_reordering_moves_primacy_with_the_first_entry(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        """Position and primacy belong to the list, not to a row."""
        one = make_asset(tenant, "one.jpg")
        two = make_asset(tenant, "two.jpg")

        for payload in ([one, two], [two, one]):
            admin_client.patch(
                f"/api/v1/admin/products/{product.pk}/",
                {"image_ids": [str(a.pk) for a in payload]},
                content_type="application/json",
            )

        rows = list(ProductImage.objects.filter(product=product).order_by("position"))
        assert [row.asset_id for row in rows] == [two.pk, one.pk]
        assert rows[0].is_primary is True
        assert rows[1].is_primary is False

    def test_exactly_one_primary_survives_a_replacement(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        assets = [make_asset(tenant, f"{i}.jpg") for i in range(4)]

        admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": [str(a.pk) for a in assets]},
            content_type="application/json",
        )

        primaries = ProductImage.objects.filter(product=product, is_primary=True).count()
        assert primaries == 1

    def test_an_empty_list_clears_the_images(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        asset = make_asset(tenant, "one.jpg")
        admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": [str(asset.pk)]},
            content_type="application/json",
        )

        admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": []},
            content_type="application/json",
        )

        assert ProductImage.objects.filter(product=product).count() == 0

    def test_omitting_the_field_leaves_images_alone(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        """Not mentioning images is different from asking for none.

        A form that edits only the name must not wipe the gallery.
        """
        asset = make_asset(tenant, "one.jpg")
        admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": [str(asset.pk)]},
            content_type="application/json",
        )

        admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"name": "Renamed but still illustrated"},
            content_type="application/json",
        )

        assert ProductImage.objects.filter(product=product).count() == 1

    def test_images_are_returned_after_attaching(
        self, admin_client: Any, product: Any, tenant: Any
    ) -> None:
        asset = make_asset(tenant, "one.jpg")
        response = admin_client.patch(
            f"/api/v1/admin/products/{product.pk}/",
            {"image_ids": [str(asset.pk)]},
            content_type="application/json",
        )

        assert len(response.json()["images"]) == 1
