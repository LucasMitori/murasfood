"""Asynchronous media processing."""

from __future__ import annotations

import contextlib
import logging
from io import BytesIO
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db.models import Q

from .models import AssetStatus, MediaAsset
from .storage import get_storage

logger = logging.getLogger("murasfood.media")

#: WebP at this quality is visually indistinguishable from the original for
#: product photography while being far smaller than JPEG.
WEBP_QUALITY = 82

#: AVIF carries more detail per byte, so a lower number here is not a worse
#: picture — it is roughly WebP's 82 at about two thirds of the size.
AVIF_QUALITY = 60

#: The master is a source for future derivatives rather than something anyone
#: looks at, so it can afford to be generous.
MASTER_QUALITY = 88


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

            # AVIF under a prefixed name, so `derivatives` keeps the shape every
            # existing reader expects and the extra entries are simply ignored
            # by anything that does not know about them.
            if settings.MEDIA_IMAGE_AVIF:
                avif = BytesIO()
                resized.save(avif, format="AVIF", quality=AVIF_QUALITY)
                avif.seek(0)

                avif_key = f"{stem}_{name}.avif"
                storage.save(avif_key, avif, content_type="image/avif", public=asset.is_public)
                derivatives[f"avif_{name}"] = avif_key

        master = _shrink_master(asset, original, storage)

        asset.placeholder = _placeholder(original)
        asset.derivatives = derivatives
        asset.width = master[0]
        asset.height = master[1]
        asset.status = AssetStatus.READY
        asset.save(
            update_fields=[
                "derivatives",
                "placeholder",
                "width",
                "height",
                "size_bytes",
                "content_type",
                "storage_key",
                "status",
                "updated_at",
            ]
        )

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


def _shrink_master(asset: MediaAsset, original: Any, storage: Any) -> tuple[int, int]:
    """Replace the stored original with a capped, re-encoded master.

    Nothing renders the original: the storefront picks a derivative, and the
    widest of those is 1280px. Keeping a 4000x3000 phone photo means paying to
    store six megabytes that are never read — ninety per cent of what an upload
    costs, measured on a real one.

    So the master is capped at `MEDIA_IMAGE_MAX_DIMENSION` and written as WebP,
    which leaves plenty of headroom above every derivative while costing a
    fraction of the space. Set the dimension to 0 to keep originals as uploaded.

    Returns the master's dimensions. Mutates `asset` in memory only — the caller
    saves, so a failure here cannot leave the row pointing at a file that was
    never written.
    """
    limit = settings.MEDIA_IMAGE_MAX_DIMENSION
    if not limit or max(original.width, original.height) <= limit:
        return original.width, original.height

    from PIL import Image

    ratio = limit / max(original.width, original.height)
    size = (max(1, round(original.width * ratio)), max(1, round(original.height * ratio)))
    master = original.resize(size, Image.LANCZOS)

    buffer = BytesIO()
    master.save(buffer, format="WEBP", quality=MASTER_QUALITY, method=4)
    buffer.seek(0)
    content = buffer.getvalue()

    stem = asset.storage_key.rsplit(".", 1)[0]
    key = f"{stem}_master.webp"
    storage.save(key, BytesIO(content), content_type="image/webp", public=asset.is_public)

    # The old file goes only once the new one is safely stored, so an
    # interruption leaves a spare copy rather than an asset with no image.
    previous = asset.storage_key
    asset.storage_key = key
    asset.content_type = "image/webp"
    asset.size_bytes = len(content)

    with contextlib.suppress(Exception):
        storage.delete(previous)

    logger.info(
        "image_master_shrunk",
        extra={"event": "media.master_shrunk", "asset_id": str(asset.pk), "bytes": len(content)},
    )
    return size


def _unreferenced() -> Q:
    """Match assets nothing points at, deriving the relations from the model.

    This list used to be written out by hand, and it had fallen two behind:
    `brand_logos` and `report_jobs` were added later and never added here. Since
    the filter decides what gets *deleted*, each omission made a live file
    collectable — a brand's logo, or a report a merchant could still download.

    Reading the relations off `_meta` instead means a new one protects its
    assets from the moment it exists, without anyone having to remember this
    function.
    """
    query = Q()
    for field in MediaAsset._meta.get_fields():
        if field.auto_created and not field.concrete:
            query &= Q(**{f"{field.get_accessor_name()}__isnull": True})
    return query


@shared_task(name="apps.media.tasks.cleanup_orphaned_assets")
def cleanup_orphaned_assets(older_than_hours: int = 24) -> int:
    """Delete assets that were never attached to anything.

    A merchant who opens the product form, uploads a photo and abandons the page
    leaves an orphan. Without this the bucket grows forever.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .services import delete_asset

    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    orphans = MediaAsset.objects.filter(created_at__lt=cutoff).filter(_unreferenced()).distinct()

    removed = 0
    for asset in list(orphans[:500]):
        delete_asset(asset)
        removed += 1

    logger.info("orphaned_assets_removed", extra={"event": "media.cleanup", "count": removed})
    return removed


def _placeholder(original: Any) -> str:
    """A handful of pixels, base64'd, to show while the real photo arrives.

    The frame already reserves its space from the aspect ratio, so this is not
    about layout shift — it is about what fills that space in the meantime. A
    flat grey rectangle with an icon in it looks like a picture that failed; a
    blurred wash of the right colours looks like a picture that is arriving, and
    on a grid of forty products that is the difference between "slow" and
    "loading".

    Returned as a data URI so it travels inside the JSON the card already
    fetches. A separate file would be a request per product, which would cost
    more than it saves.

    Never raises: a shop losing its blur placeholders is a cosmetic
    disappointment, and failing the whole derivative job over one would cost it
    every variant.
    """
    import base64

    from PIL import Image

    width = settings.MEDIA_IMAGE_PLACEHOLDER_WIDTH
    if not width or width < 4:
        return ""

    try:
        ratio = width / original.width
        size = (width, max(1, round(original.height * ratio)))
        tiny = original.convert("RGB").resize(size, Image.BILINEAR)

        buffer = BytesIO()
        # Quality is deliberately low: it is going to be blurred and stretched
        # over the whole frame, so detail is wasted bytes in the HTML.
        tiny.save(buffer, format="WEBP", quality=40, method=0)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        logger.warning("placeholder_failed", extra={"event": "media.placeholder_failed"})
        return ""

    return f"data:image/webp;base64,{encoded}"
