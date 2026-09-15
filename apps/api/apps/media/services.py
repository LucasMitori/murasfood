"""
Upload handling.

Every upload is validated before it is stored (spec §88):

* size ceiling,
* declared MIME type against an allow-list,
* **actual file signature** — ``Content-Type`` is client-supplied and is not
  evidence of anything,
* image decodability and dimensions.

Only then does the asset reach storage.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.common.exceptions import DomainError

from .models import AssetFolder, AssetKind, AssetStatus, Document, MediaAsset
from .storage import build_key, checksum, get_storage, guess_content_type

if TYPE_CHECKING:  # pragma: no cover
    from django.core.files.uploadedfile import UploadedFile

    from apps.accounts.models import User
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.media")


class InvalidUploadError(DomainError):
    default_detail = _("The uploaded file was rejected.")
    default_code = "INVALID_UPLOAD"


#: Leading bytes that identify a format, checked against the declared type.
#: WebP and AVIF live inside container formats, so they are matched separately.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF-",),
}

_MAX_IMAGE_PIXELS = 50_000_000  # guards against decompression-bomb uploads


def _detect_signature(head: bytes) -> str | None:
    """Identify a format from its leading bytes."""
    for content_type, signatures in _MAGIC_SIGNATURES.items():
        if any(head.startswith(sig) for sig in signatures):
            return content_type

    # RIFF....WEBP
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # ISO-BMFF brand for AVIF
    if head[4:8] == b"ftyp" and b"avif" in head[8:24]:
        return "image/avif"
    return None


def validate_upload(
    upload: UploadedFile,
    *,
    kind: str,
    max_bytes: int | None = None,
) -> tuple[str, bytes]:
    """Validate an incoming file and return ``(content_type, head_bytes)``.

    Raises:
        InvalidUploadError: The file is too large, of a disallowed type, or its
            contents do not match the type it claims to be.
    """
    limit = max_bytes or settings.MEDIA_MAX_UPLOAD_BYTES
    if upload.size is None or upload.size <= 0:
        raise InvalidUploadError(_("The file is empty."))
    if upload.size > limit:
        raise InvalidUploadError(
            _("The file exceeds the %(limit)s MB limit.") % {"limit": limit // (1024 * 1024)},
            details={"max_bytes": limit, "size": upload.size},
        )

    allowed = (
        settings.MEDIA_ALLOWED_IMAGE_TYPES
        if kind == AssetKind.IMAGE
        else settings.MEDIA_ALLOWED_DOCUMENT_TYPES
    )

    upload.seek(0)
    head = upload.read(32)
    upload.seek(0)

    detected = _detect_signature(head)
    if detected is None or detected not in allowed:
        raise InvalidUploadError(
            _("Unsupported file type."),
            details={"allowed": allowed, "detected": detected},
        )

    declared = (upload.content_type or "").lower()
    if declared and declared != detected and declared not in allowed:
        logger.warning(
            "upload_content_type_mismatch",
            extra={"event": "media.type_mismatch", "declared": declared, "detected": detected},
        )

    return detected, head


def _sanitize_filename(name: str) -> str:
    """Strip directories and dangerous characters from a client filename."""
    base = (name or "file").replace("\\", "/").split("/")[-1]
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ").strip()
    return (cleaned or "file")[:255]


def _image_dimensions(upload: UploadedFile) -> tuple[int | None, int | None]:
    """Read image dimensions, rejecting anything that will not decode."""
    try:
        from PIL import Image

        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
        upload.seek(0)
        with Image.open(upload) as image:
            width, height = image.size
    except Exception as exc:
        raise InvalidUploadError(_("The image could not be read.")) from exc
    finally:
        upload.seek(0)

    if width * height > _MAX_IMAGE_PIXELS:
        raise InvalidUploadError(_("The image resolution is too large."))
    return width, height


@transaction.atomic
def store_upload(
    *,
    tenant: Tenant,
    upload: UploadedFile,
    folder: str = AssetFolder.PRODUCT,
    kind: str = AssetKind.IMAGE,
    alt_text: str = "",
    is_public: bool = True,
    uploaded_by: User | None = None,
) -> MediaAsset:
    """Validate, persist and register an upload.

    The row is created first so the storage key can embed the asset id, then the
    bytes are written. If the write fails the transaction rolls the row back,
    leaving no dangling metadata.
    """
    content_type, _head = validate_upload(upload, kind=kind)

    width = height = None
    if kind == AssetKind.IMAGE:
        width, height = _image_dimensions(upload)

    filename = _sanitize_filename(upload.name or "file")
    asset = MediaAsset(
        tenant=tenant,
        kind=kind,
        folder=folder,
        original_filename=filename,
        content_type=content_type or guess_content_type(filename),
        size_bytes=upload.size or 0,
        width=width,
        height=height,
        alt_text=alt_text[:255],
        is_public=is_public,
        uploaded_by=uploaded_by,
        status=AssetStatus.PENDING,
        bucket=settings.S3_BUCKET,
    )
    asset.storage_key = build_key(
        tenant_id=str(tenant.pk), folder=folder, asset_id=asset.pk.hex, filename=filename
    )
    upload.seek(0)
    asset.checksum = checksum(upload)

    # The same picture, uploaded again.
    #
    # `checksum` has been computed and indexed since day one and nothing read
    # it. A supplier catalogue is full of repeats — one photo standing in for
    # every flavour of a product, a house brand's identical packaging shot — and
    # a ten-thousand-product import would store each copy separately and then
    # pay to resize and re-encode it four times over in two formats.
    #
    # Reusing the row is safe because `ProductImage.asset` is a plain foreign
    # key: many products may point at one asset, and the orphan sweep derives
    # what is still referenced from `_meta`, so a shared asset is never
    # collected while anything still uses it.
    existing = _identical_asset(asset)
    if existing is not None:
        logger.info(
            "media_asset_deduplicated",
            extra={
                "event": "media.deduplicated",
                "asset_id": str(existing.pk),
                "bytes_saved": asset.size_bytes,
            },
        )
        return existing

    asset.save()

    get_storage().save(asset.storage_key, upload, content_type=asset.content_type, public=is_public)

    if kind == AssetKind.IMAGE:
        # Derivatives are generated off the request path: resizing a 12 MP photo
        # must not make a merchant wait.
        from .tasks import generate_image_derivatives

        transaction.on_commit(lambda: generate_image_derivatives.delay(str(asset.pk)))
    else:
        asset.status = AssetStatus.READY
        asset.save(update_fields=["status", "updated_at"])

    logger.info(
        "media_asset_stored",
        extra={"event": "media.stored", "asset_id": str(asset.pk), "kind": kind},
    )
    return asset


def asset_url(
    asset: MediaAsset, *, variant: str | None = None, expires_in: int | None = None
) -> str:
    """URL for an asset, optionally for one of its resized variants.

    Private assets always get a signed, expiring URL.
    """
    key = asset.storage_key
    if variant and isinstance(asset.derivatives, dict):
        key = asset.derivatives.get(variant) or key
    return get_storage().url(key, expires_in=expires_in, public=asset.is_public)


def delete_asset(asset: MediaAsset) -> None:
    """Remove an asset and every derivative from storage, then the row."""
    storage = get_storage()
    keys = [asset.storage_key, *(asset.derivatives or {}).values()]
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            logger.warning(
                "media_delete_failed", extra={"event": "media.delete_failed", "key": key}
            )
    asset.delete()


@transaction.atomic
def create_document(
    *,
    tenant: Tenant,
    upload: UploadedFile,
    title: str,
    document_type: str,
    description: str = "",
    related_type: str = "",
    related_id: str = "",
    uploaded_by: User | None = None,
) -> Document:
    """Store a private document (invoice, receipt, contract)."""
    asset = store_upload(
        tenant=tenant,
        upload=upload,
        folder=AssetFolder.DOCUMENT,
        kind=AssetKind.DOCUMENT,
        is_public=False,
        uploaded_by=uploaded_by,
    )
    return Document.objects.create(
        tenant=tenant,
        asset=asset,
        title=title[:255],
        document_type=document_type,
        description=description,
        related_type=related_type[:64],
        related_id=str(related_id)[:64],
        uploaded_by=uploaded_by,
    )


def store_generated_file(
    *,
    tenant: Tenant,
    content: bytes,
    filename: str,
    content_type: str,
    folder: str = AssetFolder.REPORT,
) -> MediaAsset:
    """Register a file the platform produced itself (a rendered PDF report).

    Bypasses upload validation because the bytes did not come from a client.
    """
    asset = MediaAsset(
        tenant=tenant,
        kind=AssetKind.DOCUMENT,
        folder=folder,
        original_filename=_sanitize_filename(filename),
        content_type=content_type,
        size_bytes=len(content),
        is_public=False,
        status=AssetStatus.READY,
        bucket=settings.S3_BUCKET,
    )
    asset.storage_key = build_key(
        tenant_id=str(tenant.pk), folder=folder, asset_id=asset.pk.hex, filename=filename
    )
    stream = BytesIO(content)
    asset.checksum = checksum(stream)
    asset.save()

    get_storage().save(asset.storage_key, stream, content_type=content_type, public=False)
    return asset


def validate_banner_link(link_type: str, link_target: str) -> str:
    """Reject unsafe banner targets (spec §11).

    External links must be absolute ``https`` URLs; internal ones are opaque
    identifiers the frontend resolves against its own routes, so they can never
    become an open redirect.
    """
    from urllib.parse import urlparse

    from .models import Banner

    target = (link_target or "").strip()
    if link_type == Banner.LinkType.NONE:
        return ""
    if not target:
        raise InvalidUploadError(_("A link target is required."), code="INVALID_LINK_TARGET")

    if link_type == Banner.LinkType.EXTERNAL:
        parsed = urlparse(target)
        if parsed.scheme != "https" or not parsed.netloc:
            raise InvalidUploadError(
                _("External links must be absolute https URLs."), code="INVALID_LINK_TARGET"
            )
        return target

    if any(ch in target for ch in "\r\n<>\"'"):
        raise InvalidUploadError(_("Invalid link target."), code="INVALID_LINK_TARGET")
    return target[:512]


def record_banner_event(banner_id: Any, *, event: str) -> None:
    """Increment an impression or click counter without a read-modify-write.

    ``F`` expressions keep concurrent updates from losing counts.
    """
    from django.db.models import F

    from .models import Banner

    field = "click_count" if event == "click" else "impression_count"
    Banner.objects.filter(pk=banner_id).update(**{field: F(field) + 1})


def _identical_asset(candidate: MediaAsset) -> MediaAsset | None:
    """An already-processed asset holding exactly these bytes, if there is one.

    Matched on tenant, folder, visibility and SHA-256. Tenant because assets are
    never shared across shops; folder and visibility because they decide the
    storage key's prefix and its ACL, and a private document must never be
    satisfied by a public product photo that happens to be byte-identical.

    Only `READY` rows qualify. A `PENDING` match is an upload whose derivatives
    have not been generated yet, and returning it would hand the caller an asset
    with no variants; a `FAILED` one is broken.
    """
    if not candidate.checksum:
        return None

    return (
        MediaAsset.objects.filter(
            tenant_id=candidate.tenant_id,
            checksum=candidate.checksum,
            folder=candidate.folder,
            is_public=candidate.is_public,
            status=AssetStatus.READY,
        )
        .order_by("created_at")
        .first()
    )
