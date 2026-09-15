"""
The image pipeline at ten thousand products.

The conversions themselves were already covered. What was not, and what actually
decides whether a market with 10,000 products has a fast shop or a slow one:

* every derivative is cached forever by the browser, so a returning shopper
  re-downloads nothing;
* the same photograph uploaded twice is stored once, because a supplier
  catalogue repeats images constantly;
* something is on screen before the real photo decodes.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.media.models import AssetFolder, AssetStatus, MediaAsset
from apps.media.services import store_upload

pytestmark = pytest.mark.django_db


def photo(
    colour: tuple[int, int, int] = (120, 40, 50),
    size: tuple[int, int] = (900, 600),
) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def upload(tenant: Any, data: bytes, name: str = "photo.jpg", **kwargs: Any) -> MediaAsset:
    return store_upload(
        tenant=tenant,
        upload=SimpleUploadedFile(name, data, content_type="image/jpeg"),
        folder=kwargs.pop("folder", AssetFolder.PRODUCT),
        **kwargs,
    )


class TestDeduplication:
    def test_the_same_bytes_are_stored_once(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """A supplier catalogue repeats one photo across a dozen flavours. Ten
        thousand products would otherwise pay to store and re-encode each copy."""
        data = photo()

        with django_capture_on_commit_callbacks(execute=True):
            first = upload(tenant, data, "a.jpg")

        second = upload(tenant, data, "b.jpg")

        assert first.pk == second.pk
        assert MediaAsset.objects.count() == 1

    def test_different_bytes_are_different_assets(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            first = upload(tenant, photo((10, 20, 30)), "a.jpg")
        with django_capture_on_commit_callbacks(execute=True):
            second = upload(tenant, photo((200, 100, 40)), "b.jpg")

        assert first.pk != second.pk

    def test_a_private_document_is_never_satisfied_by_a_public_image(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """Visibility decides the ACL, so a byte-identical public photo must not
        stand in for a private one."""
        data = photo()

        with django_capture_on_commit_callbacks(execute=True):
            public = upload(tenant, data, "a.jpg", is_public=True)
        private = upload(tenant, data, "b.jpg", is_public=False)

        assert public.pk != private.pk

    def test_one_shop_never_reuses_another_shops_asset(
        self, tenant: Any, other_tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        data = photo()

        with django_capture_on_commit_callbacks(execute=True):
            mine = upload(tenant, data, "a.jpg")
        theirs = upload(other_tenant, data, "a.jpg")

        assert mine.pk != theirs.pk

    def test_an_unprocessed_match_is_not_reused(self, tenant: Any) -> None:
        """A `PENDING` row has no derivatives yet; handing it back would give the
        caller an asset with no variants to render."""
        data = photo()

        first = upload(tenant, data, "a.jpg")
        assert first.status == AssetStatus.PENDING

        second = upload(tenant, data, "b.jpg")

        assert first.pk != second.pk


class TestPlaceholder:
    def test_a_processed_image_carries_a_blurred_stand_in(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            asset = upload(tenant, photo())

        asset.refresh_from_db()

        assert asset.placeholder.startswith("data:image/webp;base64,")

    def test_it_is_small_enough_to_inline_forty_times(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """It travels in the JSON of every product card. A grid of forty must
        cost less than one thumbnail, or the cure is worse than the disease."""
        with django_capture_on_commit_callbacks(execute=True):
            asset = upload(tenant, photo())

        asset.refresh_from_db()
        encoded = asset.placeholder.split(",", 1)[1]

        assert len(base64.b64decode(encoded)) < 1024

    def test_the_public_payload_carries_it(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """A field generated and never serialised is a field that does nothing."""
        from apps.media.serializers import MediaAssetSerializer

        with django_capture_on_commit_callbacks(execute=True):
            asset = upload(tenant, photo())

        asset.refresh_from_db()
        data = MediaAssetSerializer(asset).data

        assert data["placeholder"] == asset.placeholder


class TestCacheHeaders:
    def test_public_derivatives_are_cached_forever(self, settings: Any) -> None:
        """The largest rendering cost in the pipeline, and it was simply absent:
        every derivative went up with no caching policy, so a returning shopper
        re-fetched every photo on the page."""
        from unittest import mock

        from apps.media.storage import S3CompatibleStorage

        with mock.patch.object(S3CompatibleStorage, "__init__", return_value=None):
            backend = S3CompatibleStorage()
        backend.bucket = "test"
        backend._client = mock.Mock()

        backend.save("key.webp", BytesIO(b"x"), content_type="image/webp", public=True)

        extra = backend._client.upload_fileobj.call_args.kwargs["ExtraArgs"]
        assert extra["CacheControl"] == f"public, max-age={settings.MEDIA_CACHE_MAX_AGE}, immutable"
        assert extra["ACL"] == "public-read"

    def test_private_objects_are_never_cached(self) -> None:
        """They are reached through a short-lived signed URL, and a shared cache
        holding a copy would outlive the signature meant to bound access."""
        from unittest import mock

        from apps.media.storage import S3CompatibleStorage

        with mock.patch.object(S3CompatibleStorage, "__init__", return_value=None):
            backend = S3CompatibleStorage()
        backend.bucket = "test"
        backend._client = mock.Mock()

        backend.save("report.pdf", BytesIO(b"x"), content_type="application/pdf", public=False)

        extra = backend._client.upload_fileobj.call_args.kwargs["ExtraArgs"]
        assert extra["CacheControl"] == "private, no-store"
        assert "ACL" not in extra
