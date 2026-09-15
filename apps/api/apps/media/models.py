"""
Media and document models.

The database stores *metadata* only — key, bucket, MIME type, size, dimensions,
checksum, alt text. The bytes live in object storage (spec §10, §27).
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class AssetKind(models.TextChoices):
    IMAGE = "IMAGE", _("Image")
    DOCUMENT = "DOCUMENT", _("Document")


class AssetStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending processing")
    READY = "READY", _("Ready")
    FAILED = "FAILED", _("Processing failed")


class AssetFolder(models.TextChoices):
    """Logical grouping, which also becomes the storage key prefix."""

    PRODUCT = "products", _("Product images")
    BANNER = "banners", _("Banners")
    BRANDING = "branding", _("Branding")
    CATEGORY = "categories", _("Category images")
    DOCUMENT = "documents", _("Documents")
    REPORT = "reports", _("Generated reports")
    AVATAR = "avatars", _("Profile pictures")


class DocumentType(models.TextChoices):
    INVOICE = "INVOICE", _("Invoice")
    RECEIPT = "RECEIPT", _("Receipt")
    REPORT = "REPORT", _("Report")
    CONTRACT = "CONTRACT", _("Contract")
    PRODUCT_SHEET = "PRODUCT_SHEET", _("Product sheet")
    OTHER = "OTHER", _("Other")


class MediaAsset(TenantOwnedModel):
    """An uploaded image or file.

    ``derivatives`` holds ``{"thumbnail": "<key>", ...}`` for resized variants
    produced asynchronously, so the storefront can request the smallest image
    that fits the layout.
    """

    kind = models.CharField(
        _("kind"), max_length=16, choices=AssetKind.choices, default=AssetKind.IMAGE
    )
    folder = models.CharField(
        _("folder"), max_length=32, choices=AssetFolder.choices, default=AssetFolder.PRODUCT
    )
    status = models.CharField(
        _("status"), max_length=16, choices=AssetStatus.choices, default=AssetStatus.PENDING
    )

    storage_key = models.CharField(_("storage key"), max_length=512, unique=True)
    bucket = models.CharField(_("bucket"), max_length=128, blank=True)
    original_filename = models.CharField(_("original filename"), max_length=255)
    content_type = models.CharField(_("MIME type"), max_length=128)
    size_bytes = models.PositiveIntegerField(_("size in bytes"), default=0)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True, db_index=True)

    width = models.PositiveIntegerField(_("width"), null=True, blank=True)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True)
    alt_text = models.CharField(
        _("alt text"),
        max_length=255,
        blank=True,
        help_text=_("Required for accessibility on anything user-visible."),
    )

    derivatives = models.JSONField(_("derivatives"), default=dict, blank=True)
    placeholder = models.TextField(
        _("placeholder"),
        blank=True,
        help_text=_(
            "A tiny blurred copy as a data URI, shown while the real image "
            "decodes. Stored on the row rather than as a file so it arrives "
            "with the JSON and costs no extra request."
        ),
    )
    is_public = models.BooleanField(
        _("public"),
        default=True,
        help_text=_("Product images are public; documents are not."),
    )

    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("media asset")
        verbose_name_plural = _("media assets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "folder", "-created_at"]),
            models.Index(fields=["tenant", "checksum"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.original_filename

    @property
    def is_image(self) -> bool:
        return self.kind == AssetKind.IMAGE


class Document(TenantOwnedModel):
    """A stored file with business meaning: invoice, receipt, report, contract.

    Documents are private by default and always served through signed URLs
    (invariants #12 and #13).
    """

    asset = models.OneToOneField(
        MediaAsset, on_delete=models.CASCADE, related_name="document", verbose_name=_("file")
    )
    document_type = models.CharField(
        _("type"), max_length=24, choices=DocumentType.choices, default=DocumentType.OTHER
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)

    # Loose association: a document may relate to an order, a product, a
    # supplier or nothing at all. A generic relation would add joins for very
    # little benefit at this scale.
    related_type = models.CharField(_("related type"), max_length=64, blank=True, db_index=True)
    related_id = models.CharField(_("related id"), max_length=64, blank=True, db_index=True)

    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "document_type", "-created_at"]),
            models.Index(fields=["related_type", "related_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.title


class Banner(TenantOwnedModel):
    """A merchandising banner on the storefront (spec §11).

    Link targets are constrained to known types; arbitrary URLs are validated
    before they are stored so a banner cannot become an open redirect.
    """

    class LinkType(models.TextChoices):
        NONE = "NONE", _("No link")
        CATEGORY = "CATEGORY", _("Category")
        PRODUCT = "PRODUCT", _("Product")
        PROMOTION = "PROMOTION", _("Promotion")
        COLLECTION = "COLLECTION", _("Collection")
        SEARCH = "SEARCH", _("Search term")
        EXTERNAL = "EXTERNAL", _("External URL")

    title = models.CharField(_("title"), max_length=160)
    subtitle = models.CharField(_("subtitle"), max_length=255, blank=True)
    image = models.ForeignKey(
        MediaAsset, on_delete=models.PROTECT, related_name="banners", verbose_name=_("image")
    )
    mobile_image = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mobile_banners",
        verbose_name=_("mobile image"),
    )

    link_type = models.CharField(
        _("link type"), max_length=16, choices=LinkType.choices, default=LinkType.NONE
    )
    link_target = models.CharField(_("link target"), max_length=512, blank=True)
    cta_label = models.CharField(
        _("button label"),
        max_length=40,
        blank=True,
        help_text=_("Leave empty to show the banner without a button."),
    )

    class TextAlign(models.TextChoices):
        LEFT = "LEFT", _("Left")
        CENTER = "CENTER", _("Centre")
        RIGHT = "RIGHT", _("Right")

    text_align = models.CharField(
        _("text alignment"), max_length=8, choices=TextAlign.choices, default=TextAlign.CENTER
    )
    overlay_opacity = models.PositiveSmallIntegerField(
        _("overlay strength"),
        default=45,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
        help_text=_(
            "Percentage of dark scrim over the image. The merchant controls it "
            "because how much a photo needs depends entirely on the photo."
        ),
    )

    start_at = models.DateTimeField(_("starts at"), null=True, blank=True)
    end_at = models.DateTimeField(_("ends at"), null=True, blank=True)
    priority = models.IntegerField(
        _("priority"), default=0, help_text=_("Higher values are shown first.")
    )
    is_active = models.BooleanField(_("active"), default=True)

    impression_count = models.PositiveIntegerField(_("impressions"), default=0)
    click_count = models.PositiveIntegerField(_("clicks"), default=0)

    class Meta:
        verbose_name = _("banner")
        verbose_name_plural = _("banners")
        ordering = ["-priority", "-created_at"]
        indexes = [models.Index(fields=["tenant", "is_active", "-priority"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.title

    def is_live(self, now: object = None) -> bool:
        """Whether the banner should be displayed at ``now``."""
        from django.utils import timezone

        moment = now or timezone.now()
        if not self.is_active:
            return False
        if self.start_at and moment < self.start_at:
            return False
        return not (self.end_at and moment > self.end_at)
