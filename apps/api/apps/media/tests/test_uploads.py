"""
Upload validation.

``Content-Type`` is client-supplied and proves nothing; the file signature is
what decides (spec §88).
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.media.models import AssetKind
from apps.media.services import InvalidUploadError, store_upload, validate_banner_link

pytestmark = pytest.mark.django_db


def png_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, (200, 120, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(content: bytes, name: str = "foto.png", content_type: str = "image/png") -> Any:
    return SimpleUploadedFile(name, content, content_type=content_type)


class TestImageUploads:
    def test_valid_png_is_stored_with_metadata(self, tenant: Any) -> None:
        asset = store_upload(tenant=tenant, upload=upload(png_bytes()))

        assert asset.content_type == "image/png"
        assert (asset.width, asset.height) == (64, 48)
        assert asset.checksum
        assert asset.storage_key.startswith(str(tenant.pk))

    def test_disguised_file_is_rejected(self, tenant: Any) -> None:
        """An executable renamed to .png must not get through."""
        with pytest.raises(InvalidUploadError):
            store_upload(
                tenant=tenant,
                upload=upload(b"MZ\x90\x00 not an image", name="evil.png"),
            )

    def test_pdf_is_not_accepted_as_an_image(self, tenant: Any) -> None:
        with pytest.raises(InvalidUploadError):
            store_upload(
                tenant=tenant,
                upload=upload(b"%PDF-1.4 fake", name="doc.png"),
                kind=AssetKind.IMAGE,
            )

    def test_empty_file_is_rejected(self, tenant: Any) -> None:
        with pytest.raises(InvalidUploadError):
            store_upload(tenant=tenant, upload=upload(b""))

    def test_oversized_file_is_rejected(self, tenant: Any, settings: Any) -> None:
        settings.MEDIA_MAX_UPLOAD_BYTES = 100

        with pytest.raises(InvalidUploadError) as exc:
            store_upload(tenant=tenant, upload=upload(png_bytes((200, 200))))
        assert exc.value.default_code == "INVALID_UPLOAD"

    def test_filename_is_sanitised(self, tenant: Any) -> None:
        asset = store_upload(tenant=tenant, upload=upload(png_bytes(), name="../../etc/passwd.png"))
        assert ".." not in asset.storage_key
        assert "/" not in asset.original_filename

    def test_derivatives_are_generated_for_large_images(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        """Resizing is deferred to ``on_commit`` so uploads stay fast.

        The callbacks are executed explicitly here because the test transaction
        never commits.
        """
        with django_capture_on_commit_callbacks(execute=True):
            asset = store_upload(tenant=tenant, upload=upload(png_bytes((1600, 1200))))
        asset.refresh_from_db()

        assert set(asset.derivatives) >= {"thumbnail", "small", "medium"}

    def test_small_images_are_not_upscaled(
        self, tenant: Any, django_capture_on_commit_callbacks: Any
    ) -> None:
        with django_capture_on_commit_callbacks(execute=True):
            asset = store_upload(tenant=tenant, upload=upload(png_bytes((100, 100))))
        asset.refresh_from_db()

        assert asset.derivatives == {}


class TestDocuments:
    def test_pdf_document_is_private(self, tenant: Any) -> None:
        from apps.media.services import create_document

        document = create_document(
            tenant=tenant,
            upload=SimpleUploadedFile(
                "nota.pdf", b"%PDF-1.4\n% fake pdf body\n", content_type="application/pdf"
            ),
            title="Nota fiscal",
            document_type="INVOICE",
        )
        assert document.asset.is_public is False
        assert document.asset.content_type == "application/pdf"

    def test_image_is_not_accepted_as_a_document(self, tenant: Any) -> None:
        from apps.media.services import create_document

        with pytest.raises(InvalidUploadError):
            create_document(
                tenant=tenant,
                upload=upload(png_bytes(), name="foto.pdf"),
                title="Falso",
                document_type="OTHER",
            )


class TestBannerLinks:
    def test_external_links_must_be_https(self) -> None:
        with pytest.raises(InvalidUploadError):
            validate_banner_link("EXTERNAL", "http://insecure.example")

    def test_javascript_urls_are_rejected(self) -> None:
        with pytest.raises(InvalidUploadError):
            validate_banner_link("EXTERNAL", "javascript:alert(1)")

    def test_valid_https_link_passes(self) -> None:
        assert validate_banner_link("EXTERNAL", "https://example.test/promo") == (
            "https://example.test/promo"
        )

    def test_internal_target_cannot_contain_control_characters(self) -> None:
        with pytest.raises(InvalidUploadError):
            validate_banner_link("CATEGORY", "padaria\r\nLocation: https://evil.test")

    def test_no_link_type_clears_the_target(self) -> None:
        assert validate_banner_link("NONE", "anything") == ""
