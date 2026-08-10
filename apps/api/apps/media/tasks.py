"""Asynchronous media processing."""

from __future__ import annotations

import logging
from io import BytesIO

from celery import shared_task
from django.conf import settings

from .models import AssetStatus, MediaAsset
from .storage import get_storage

logger = logging.getLogger("murasfood.media")

#: WebP at this quality is visually indistinguishable from the original for
#: product photography while being far smaller than JPEG.
WEBP_QUALITY = 82


@shared_task(
    name="apps.media.tasks.generate_image_derivatives",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_image_derivatives(self, asset_id: str) -> dict[str, str]:
    """Produce responsive WebP variants for an uploaded image.

    Sizes come from ``MEDIA_IMAGE_DERIVATIVES``. Variants are never upscaled: a
    400 px source produces no "large" variant, and the storefront falls back to
    the original.
    """
    asset = MediaAsset.objects.filter(pk=asset_id).first()
    if asset is None or not asset.is_image:
        return {}

    try:
        from PIL import Image

        storage = get_storage()
        with storage.open(asset.storage_key) as source:
            original = Image.open(source)
            original.load()

        if original.mode not in ("RGB", "RGBA"):
            original = original.convert("RGB")

        derivatives: dict[str, str] = {}
        stem = asset.storage_key.rsplit(".", 1)[0]

        for name, target_width in sorted(
            settings.MEDIA_IMAGE_DERIVATIVES.items(), key=lambda item: item[1]
        ):
            if original.width <= target_width:
                continue

            ratio = target_width / original.width
            size = (target_width, max(1, round(original.height * ratio)))
            resized = original.resize(size, Image.LANCZOS)

            buffer = BytesIO()
            resized.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=4)
            buffer.seek(0)

            key = f"{stem}_{name}.webp"
            storage.save(key, buffer, content_type="image/webp", public=asset.is_public)
            derivatives[name] = key

        asset.derivatives = derivatives
        asset.width = original.width
        asset.height = original.height
        asset.status = AssetStatus.READY
        asset.save(update_fields=["derivatives", "width", "height", "status", "updated_at"])

        logger.info(
            "image_derivatives_generated",
            extra={"event": "media.derivatives", "asset_id": asset_id, "count": len(derivatives)},
        )
        return derivatives

    except Exception as exc:
        logger.exception("image_processing_failed", extra={"event": "media.processing_failed"})
        MediaAsset.objects.filter(pk=asset_id).update(status=AssetStatus.FAILED)
        # A transient storage error deserves a retry; a corrupt image does not,
        # but distinguishing them reliably is not worth the complexity here.
        raise self.retry(exc=exc) from exc


@shared_task(name="apps.media.tasks.cleanup_orphaned_assets")
def cleanup_orphaned_assets(older_than_hours: int = 24) -> int:
    """Delete assets that were never attached to anything.

    A merchant who opens the product form, uploads a photo and abandons the page
    leaves an orphan. Without this the bucket grows forever.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from .services import delete_asset

    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    orphans = (
        MediaAsset.objects.filter(created_at__lt=cutoff)
        .filter(
            Q(product_images__isnull=True)
            & Q(banners__isnull=True)
            & Q(mobile_banners__isnull=True)
            & Q(document__isnull=True)
            & Q(category_images__isnull=True)
            & Q(branding_logos__isnull=True)
            & Q(branding_dark_logos__isnull=True)
            & Q(branding_favicons__isnull=True)
        )
        .distinct()
    )

    removed = 0
    for asset in list(orphans[:500]):
        delete_asset(asset)
        removed += 1

    logger.info("orphaned_assets_removed", extra={"event": "media.cleanup", "count": removed})
    return removed
