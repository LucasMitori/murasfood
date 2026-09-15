"""
Tenant models.

A tenant is one merchant. Everything that makes MurasFood look and behave like
a specific business — name, colours, logo, opening hours, currency, tax rules —
lives here, in the database, never in code (spec §2 and §66). That is what makes
the product white-label: onboarding a new merchant is a row, not a fork.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message=_("Enter a valid hexadecimal colour, for example #7B2D3B."),
)

SLUG_VALIDATOR = RegexValidator(
    regex=r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])$",
    message=_("Use lowercase letters, numbers and hyphens."),
)


class TenantStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    SUSPENDED = "SUSPENDED", _("Suspended")
    ARCHIVED = "ARCHIVED", _("Archived")


class Weekday(models.IntegerChoices):
    """ISO-8601 weekday numbering (Monday = 1)."""

    MONDAY = 1, _("Monday")
    TUESDAY = 2, _("Tuesday")
    WEDNESDAY = 3, _("Wednesday")
    THURSDAY = 4, _("Thursday")
    FRIDAY = 5, _("Friday")
    SATURDAY = 6, _("Saturday")
    SUNDAY = 7, _("Sunday")


class Tenant(BaseModel):
    """A merchant operating on the platform."""

    # --- Identity ------------------------------------------------------------
    slug = models.SlugField(
        _("slug"),
        max_length=50,
        unique=True,
        validators=[SLUG_VALIDATOR],
        help_text=_("Used for subdomain and API routing."),
    )
    legal_name = models.CharField(_("legal name"), max_length=255)
    trade_name = models.CharField(_("trade name"), max_length=255)
    tax_id = models.CharField(
        _("tax id"),
        max_length=32,
        blank=True,
        help_text=_("CNPJ in Brazil. Stored as typed; formatting is a display concern."),
    )

    # --- Contact -------------------------------------------------------------
    support_email = models.EmailField(_("support email"))
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    whatsapp = models.CharField(_("whatsapp"), max_length=32, blank=True)

    # --- Address -------------------------------------------------------------
    postal_code = models.CharField(_("postal code"), max_length=16, blank=True)
    street = models.CharField(_("street"), max_length=255, blank=True)
    number = models.CharField(_("number"), max_length=32, blank=True)
    complement = models.CharField(_("complement"), max_length=120, blank=True)
    neighborhood = models.CharField(_("neighborhood"), max_length=120, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    state = models.CharField(_("state"), max_length=64, blank=True)
    country = models.CharField(_("country"), max_length=2, default="BR")
    latitude = models.DecimalField(
        _("latitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        _("longitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )

    # --- Locale --------------------------------------------------------------
    timezone = models.CharField(
        _("timezone"),
        max_length=64,
        default="America/Sao_Paulo",
        help_text=_("Determines the business day used by every report."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="BRL")
    locale = models.CharField(_("locale"), max_length=10, default="pt-BR")

    # --- Lifecycle -----------------------------------------------------------
    status = models.CharField(
        _("status"), max_length=16, choices=TenantStatus.choices, default=TenantStatus.ACTIVE
    )
    is_active = models.BooleanField(_("active"), default=True)
    custom_domain = models.CharField(_("custom domain"), max_length=255, blank=True, db_index=True)

    class Meta:
        verbose_name = _("tenant")
        verbose_name_plural = _("tenants")
        ordering = ["trade_name"]
        indexes = [
            models.Index(fields=["is_active", "slug"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return self.trade_name or self.slug

    @property
    def is_operational(self) -> bool:
        """Whether the tenant may take orders at all."""
        return self.is_active and self.status == TenantStatus.ACTIVE


class TenantBranding(BaseModel):
    """Visual identity. Consumed by the storefront to theme itself at runtime.

    Colours are stored as hex so the frontend can feed them straight into the
    Vuetify theme without a build step. Defaults are the neutral MurasFood
    palette — soft white with a deep wine accent — and carry no merchant
    identity of their own.
    """

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="branding", verbose_name=_("tenant")
    )
    logo = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branding_logos",
        verbose_name=_("logo"),
    )
    logo_dark = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branding_dark_logos",
        verbose_name=_("logo (dark theme)"),
    )
    favicon = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branding_favicons",
        verbose_name=_("favicon"),
    )

    # Defaults mirror the shipped theme (see `apps/web/app/utils/theme.ts`). A
    # merchant who never opens the branding screen should get the product's own
    # palette, not a stale copy of an older one.
    primary_color = models.CharField(
        _("primary colour"), max_length=7, default="#8C1425", validators=[HEX_COLOR_VALIDATOR]
    )
    secondary_color = models.CharField(
        _("secondary colour"), max_length=7, default="#211E1F", validators=[HEX_COLOR_VALIDATOR]
    )
    accent_color = models.CharField(
        _("accent colour"), max_length=7, default="#B02233", validators=[HEX_COLOR_VALIDATOR]
    )
    dark_primary_color = models.CharField(
        _("primary colour (dark)"),
        max_length=7,
        # Lighter than the light-theme wine on purpose: a colour deep enough for
        # white paper is unreadable on near-black.
        default="#E2495D",
        validators=[HEX_COLOR_VALIDATOR],
    )

    tagline = models.CharField(_("tagline"), max_length=160, blank=True)
    about = models.TextField(_("about"), blank=True)
    instagram_url = models.URLField(_("Instagram"), blank=True)
    facebook_url = models.URLField(_("Facebook"), blank=True)
    website_url = models.URLField(_("website"), blank=True)

    class Meta:
        verbose_name = _("tenant branding")
        verbose_name_plural = _("tenant branding")

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.tenant} branding"


#: Shortcuts the floating button can offer. The catalogue lives here rather
#: than in the frontend because it is what the API validates against — a client
#: that invents a key must be refused, not quietly ignored.
FLOATING_TOOL_KEYS = ("calculator", "whatsapp", "cart", "lists", "theme", "top")

FLOATING_POSITIONS = ("bottom-right", "bottom-left", "top-right", "top-left")


def default_floating_tools() -> dict:
    """Everything on, in the order a shop is most likely to want it.

    A callable rather than a literal: a mutable default on a model field is
    shared between every row that uses it, so one tenant editing their tools
    would edit everyone's.
    """
    return {
        "enabled": True,
        "icon": "mdi-apps",
        "color": "primary",
        "position": "bottom-right",
        "actions": list(FLOATING_TOOL_KEYS),
    }


#: The rails the home page can show, in the order a new shop gets them. The
#: hero is not here: it is the banners, and a shop that has none already falls
#: back to its own name rather than to an empty band.
HOME_SECTION_KEYS = (
    "categories",
    "on_sale",
    "featured",
    "best_sellers",
    "new_arrivals",
    # What the shop has run out of, ranked by how many people asked to be told
    # when it returns. A rail a shop can switch off, like the others — some
    # merchants would rather not advertise their gaps, and that is their call.
    "back_soon",
)

#: A rail showing more than this is no longer a rail; it is the catalogue.
HOME_SECTION_MAX_LIMIT = 24

#: Parallax bands are identified by this prefix plus a stable suffix the client
#: generates. They live in the same ordered list as the rails rather than in a
#: second one, because the order *is* the page — two lists interleaved by a
#: position field would be the same information, harder to read and easier to
#: get wrong.
PARALLAX_PREFIX = "parallax:"

#: Full-height for the opening band, a shorter one for the breaks between
#: content. Anything else reads as an accident rather than a choice.
PARALLAX_HEIGHTS = (70, 100)

#: Enough for a shop with something to say, few enough that the page stays a
#: shop rather than a brochure.
PARALLAX_MAX_BANDS = 6


def is_parallax(key: str) -> bool:
    return str(key).startswith(PARALLAX_PREFIX)


def default_home_layout() -> list[dict]:
    """Every rail on, in the order the page has always rendered them.

    A callable for the same reason as `default_floating_tools`: a mutable
    default on a model field is shared between every row that uses it.

    The shape carries a `title` that is empty by default — an empty title means
    "use the translated one", so a shop that never touches this screen still
    gets copy in the visitor's own language rather than a snapshot of
    Portuguese frozen at signup.
    """
    return [{"key": key, "enabled": True, "title": "", "limit": 12} for key in HOME_SECTION_KEYS]


def default_hero() -> dict:
    """How the banner carousel at the top of the page behaves.

    Parallax is off by default. It is a deliberate choice a shop makes about its
    own front page, and turning it on for everyone would change every existing
    storefront on deploy.
    """
    return {"parallax": False, "full_height": False, "overlay": 45}


class TenantSettings(BaseModel):
    """Operational configuration a merchant can change without a deploy."""

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="settings", verbose_name=_("tenant")
    )

    # --- Orders --------------------------------------------------------------
    order_number_prefix = models.CharField(_("order number prefix"), max_length=8, default="MF")

    #: Which rails and parallax bands the home page shows, in which order.
    home_layout = models.JSONField(_("home layout"), default=default_home_layout, blank=True)

    #: The banner carousel's own behaviour, which is not a band in the list
    #: above: it is always first, and a shop with no banners still gets it.
    hero = models.JSONField(_("hero"), default=default_hero, blank=True)
    allow_orders_when_closed = models.BooleanField(
        _("accept orders while closed"),
        default=True,
        help_text=_("Scheduled orders placed outside business hours."),
    )
    auto_confirm_paid_orders = models.BooleanField(_("auto-confirm paid orders"), default=True)
    max_items_per_order = models.PositiveIntegerField(_("max items per order"), default=200)

    # --- Tax -----------------------------------------------------------------
    prices_include_tax = models.BooleanField(
        _("prices include tax"),
        default=True,
        help_text=_("Brazilian retail displays tax-inclusive prices."),
    )
    default_tax_rate = models.DecimalField(
        _("default tax rate (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    # --- Inventory -----------------------------------------------------------
    allow_backorder = models.BooleanField(
        _("allow selling without stock"),
        default=False,
        help_text=_("When off, stock can never go negative (invariant #6)."),
    )
    low_stock_threshold = models.PositiveIntegerField(_("low stock threshold"), default=5)

    hide_out_of_stock = models.BooleanField(
        _("hide products that are out of stock"),
        default=False,
        help_text=_(
            "Off by default. An empty shelf a shopper can ask to be told about "
            "is a sale delayed; one they never see is a sale lost, and the shop "
            "learns nothing about the demand it missed."
        ),
    )

    # --- Notifications -------------------------------------------------------
    notify_on_new_order = models.BooleanField(_("notify staff about new orders"), default=True)
    email_sender_name = models.CharField(_("email sender name"), max_length=120, blank=True)
    email_reply_to = models.EmailField(_("reply-to"), blank=True)

    # --- Legal ---------------------------------------------------------------
    privacy_policy_url = models.URLField(_("privacy policy URL"), blank=True)
    terms_url = models.URLField(_("terms of use URL"), blank=True)

    # --- Outgoing mail -------------------------------------------------------
    #
    # Blank host means "use the platform's own server". A white-label merchant
    # who wants mail to come from their domain fills these in; everyone else
    # inherits the deployment's configuration and never sees the difference.
    smtp_host = models.CharField(_("SMTP host"), max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(_("SMTP port"), null=True, blank=True)
    smtp_username = models.CharField(_("SMTP username"), max_length=255, blank=True)
    smtp_password = models.CharField(_("SMTP password"), max_length=255, blank=True)
    smtp_use_tls = models.BooleanField(_("use TLS"), default=True)
    smtp_from_email = models.EmailField(_("from address"), blank=True)

    # --- Floating tools ------------------------------------------------------
    floating_tools = models.JSONField(
        _("floating tools"),
        default=default_floating_tools,
        help_text=_("Which shortcuts the floating button offers, and in what order."),
    )

    class Meta:
        verbose_name = _("tenant settings")
        verbose_name_plural = _("tenant settings")

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.tenant} settings"


class BusinessHours(BaseModel):
    """Opening hours for one weekday.

    Multiple rows per weekday are allowed so a merchant can model a lunch break
    (08:00–12:00 and 14:00–19:00).
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="business_hours", verbose_name=_("tenant")
    )
    weekday = models.PositiveSmallIntegerField(_("weekday"), choices=Weekday.choices)
    opens_at = models.TimeField(_("opens at"))
    closes_at = models.TimeField(_("closes at"))
    is_closed = models.BooleanField(_("closed all day"), default=False)

    class Meta:
        verbose_name = _("business hours")
        verbose_name_plural = _("business hours")
        ordering = ["weekday", "opens_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "weekday", "opens_at"],
                name="uniq_business_hours_tenant_weekday_open",
            ),
            models.CheckConstraint(
                condition=models.Q(closes_at__gt=models.F("opens_at")) | models.Q(is_closed=True),
                name="business_hours_close_after_open",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.get_weekday_display()} {self.opens_at}–{self.closes_at}"


class FaqStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PUBLISHED = "PUBLISHED", _("Published")


class FaqCategory(TenantOwnedModel):
    """A heading on the help page: Orders, Delivery, Payment.

    A model rather than a fixed list because the questions a butcher is asked
    are not the questions a bakery is asked, and a shop that cannot group its
    own answers ends up with one undifferentiated list of thirty.
    """

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140)
    icon = models.CharField(
        _("icon"),
        max_length=64,
        blank=True,
        default="mdi-help-circle-outline",
        help_text=_("Material Design Icons name, e.g. mdi-truck-outline."),
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("FAQ category")
        verbose_name_plural = _("FAQ categories")
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_faq_category_slug"),
        ]

    def __str__(self) -> str:
        return self.name


class FaqEntry(TenantOwnedModel):
    """One question and its answer.

    Draft and published are separate states rather than a boolean because the
    useful thing is writing an answer over several sittings without it being
    live in between — which an `is_active` flag also gives you, but names badly
    enough that people use it as "temporarily hidden" and lose track.
    """

    category = models.ForeignKey(
        FaqCategory,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("category"),
    )
    question = models.CharField(_("question"), max_length=255)
    answer = models.TextField(_("answer"))
    status = models.CharField(
        _("status"), max_length=10, choices=FaqStatus.choices, default=FaqStatus.DRAFT
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    #: Counted from the storefront so a merchant can see which answers are
    #: actually read — the ones nobody opens are usually the ones nobody needed.
    view_count = models.PositiveIntegerField(_("views"), default=0)

    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("FAQ entry")
        verbose_name_plural = _("FAQ entries")
        ordering = ["position", "created_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "position"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return self.question

    @property
    def is_published(self) -> bool:
        return self.status == FaqStatus.PUBLISHED
