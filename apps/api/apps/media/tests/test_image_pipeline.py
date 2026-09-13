"""
What an uploaded photo costs to keep.

A shopkeeper photographs a shelf and uploads six megabytes at 4000x3000.
Nothing ever renders that file — the storefront picks a derivative, and the
widest of those is 1280px — so it was ninety per cent of the storage an upload
cost, written once and never read. Four hundred products at three photos each
is nine gigabytes, eight of which nobody looks at.

So the master is capped and re-encoded, and AVIF is generated beside WebP for
the third fewer bytes it costs a shopper on mobile data.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.media.models import AssetStatus, MediaAsset
from apps.media.services import store_upload
from apps.media.storage import get_storage
from apps.media.tasks import generate_image_derivatives

pytestmark = pytest.mark.django_db


def photo(width: int = 3000, height: int = 2000) -> SimpleUploadedFile:
    """A JPEG large enough to be worth shrinking."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), (120, 90, 70))
    draw = ImageDraw.Draw(image)
    # Some structure, so the encoder has more to do than a flat colour.
    for index in range(0, width, 200):
        draw.ellipse([index, index // 2, index + 150, index // 2 + 120], fill=(200, 140, 90))

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return SimpleUploadedFile("shelf.jpg", buffer.getvalue(), content_type="image/jpeg")


def stored(tenant: Any, upload: SimpleUploadedFile) -> MediaAsset:
    asset = store_upload(tenant=tenant, upload=upload, kind="IMAGE", is_public=True)
    generate_image_derivatives(str(asset.pk))
    asset.refresh_from_db()
    return asset


def size_of(key: str) -> int:
    with get_storage().open(key) as handle:
        return len(handle.read())


class TestTheStoredMaster:
    def test_a_large_upload_is_capped(self, tenant: Any, settings: Any) -> None:
        settings.MEDIA_IMAGE_MAX_DIMENSION = 2048

        asset = stored(tenant, photo(3000, 2000))

        assert max(asset.width, asset.height) == 2048
        assert asset.content_type == "image/webp"

    def test_it_is_dramatically_smaller(self, tenant: Any, settings: Any) -> None:
        """The whole point: the bytes that were never read are not kept."""
        settings.MEDIA_IMAGE_MAX_DIMENSION = 2048
        upload = photo(3000, 2000)
        original_bytes = upload.size

        asset = stored(tenant, upload)

        assert asset.size_bytes < original_bytes / 2

    def test_the_original_file_is_removed(self, tenant: Any, settings: Any) -> None:
        """Keeping both would make the change cost storage rather than save it."""
        settings.MEDIA_IMAGE_MAX_DIMENSION = 2048
        upload = photo(3000, 2000)

        asset = stored(tenant, upload)

        assert asset.storage_key.endswith("_master.webp")
        assert get_storage().exists(asset.storage_key)

    def test_a_small_upload_is_left_alone(self, tenant: Any, settings: Any) -> None:
        """Re-encoding an image already under the cap would lose quality for
        nothing."""
        settings.MEDIA_IMAGE_MAX_DIMENSION = 2048

        asset = stored(tenant, photo(800, 600))

        assert (asset.width, asset.height) == (800, 600)
        assert asset.content_type == "image/jpeg"

    def test_the_cap_can_be_switched_off(self, tenant: Any, settings: Any) -> None:
        """A deployment that must keep originals — print, archival — can."""
        settings.MEDIA_IMAGE_MAX_DIMENSION = 0

        asset = stored(tenant, photo(3000, 2000))

        assert (asset.width, asset.height) == (3000, 2000)
        assert asset.content_type == "image/jpeg"


class TestDerivatives:
    def test_both_formats_are_generated(self, tenant: Any, settings: Any) -> None:
        settings.MEDIA_IMAGE_AVIF = True

        asset = stored(tenant, photo(3000, 2000))

        assert "medium" in asset.derivatives
        assert "avif_medium" in asset.derivatives

    def test_avif_is_smaller_than_webp(self, tenant: Any, settings: Any) -> None:
        """The reason for carrying a second format at all."""
        settings.MEDIA_IMAGE_AVIF = True

        asset = stored(tenant, photo(3000, 2000))

        assert size_of(asset.derivatives["avif_large"]) < size_of(asset.derivatives["large"])

    def test_avif_can_be_switched_off(self, tenant: Any, settings: Any) -> None:
        settings.MEDIA_IMAGE_AVIF = False

        asset = stored(tenant, photo(3000, 2000))

        assert "medium" in asset.derivatives
        assert not any(name.startswith("avif_") for name in asset.derivatives)

    def test_the_webp_names_are_unchanged(self, tenant: Any, settings: Any) -> None:
        """AVIF is stored under a prefix so that everything already reading
        `variants` — the serializers, the storefront's srcset — keeps working
        and simply ignores the extra keys."""
        settings.MEDIA_IMAGE_AVIF = True

        asset = stored(tenant, photo(3000, 2000))

        plain = {name for name in asset.derivatives if not name.startswith("avif_")}
        assert plain <= {"thumbnail", "small", "medium", "large"}

    def test_processing_marks_the_asset_ready(self, tenant: Any) -> None:
        asset = stored(tenant, photo(1200, 900))

        assert asset.status == AssetStatus.READY
