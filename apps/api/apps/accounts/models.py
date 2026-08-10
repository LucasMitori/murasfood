"""
Identity models.

Design notes worth keeping in mind:

* The user model is custom from day one — swapping it later is a migration
  nightmare (spec §6).
* Email is the login identifier and is unique **per tenant**, so the same person
  can shop at two merchants on the same deployment with separate accounts.
* Tokens are stored hashed. A leaked database must not hand an attacker working
  password-reset links.
* Accounts are anonymised, never hard-deleted, when orders exist: financial
  records are immutable (invariant #9, LGPD §42).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel

from .constants import (
    ALL_PERMISSION_CODES,
    PERMISSION_CATALOGUE,
    TokenPurpose,
    UserType,
)

if TYPE_CHECKING:  # pragma: no cover
    pass


class Permission(BaseModel):
    """One capability, identified by a stable code such as ``orders.refund``."""

    code = models.CharField(_("code"), max_length=64, unique=True)
    description = models.CharField(_("description"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("permission")
        verbose_name_plural = _("permissions")
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class Role(BaseModel):
    """A named bundle of permissions.

    ``tenant`` is nullable so the platform can ship system roles that every
    merchant inherits; merchant-created roles always carry a tenant.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,
        blank=True,
        verbose_name=_("tenant"),
    )
    slug = models.SlugField(_("slug"), max_length=64)
    name = models.CharField(_("name"), max_length=120)
    description = models.CharField(_("description"), max_length=255, blank=True)
    is_system = models.BooleanField(
        _("system role"),
        default=False,
        help_text=_("System roles are re-synced on deploy and cannot be deleted."),
    )
    permissions = models.ManyToManyField(
        Permission, related_name="roles", blank=True, verbose_name=_("permissions")
    )

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_role_tenant_slug"),
        ]

    def __str__(self) -> str:
        return self.name

    def permission_codes(self) -> set[str]:
        return set(self.permissions.values_list("code", flat=True))


class UserManager(BaseUserManager):
    """Manager for the email-identified custom user."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        # `set_password` hashes; a plaintext password never reaches the database.
        user.set_password(password)
        # Field-level validation only: uniqueness is enforced by the database
        # constraints, which are race-free where an ORM pre-check is not.
        user.full_clean(
            exclude=["password", "last_login"],
            validate_unique=False,
            validate_constraints=False,
        )
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("user_type", UserType.CUSTOMER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("user_type", UserType.PLATFORM_ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_verified", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """A platform account: shopper, staff member or administrator."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        verbose_name=_("tenant"),
        help_text=_("Platform administrators may have no tenant."),
    )
    email = models.EmailField(_("email"), db_index=True)
    first_name = models.CharField(_("first name"), max_length=120, blank=True)
    last_name = models.CharField(_("last name"), max_length=120, blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)

    user_type = models.CharField(
        _("type"), max_length=20, choices=UserType.choices, default=UserType.CUSTOMER
    )
    roles = models.ManyToManyField(
        Role,
        through="UserRole",
        # `UserRole` also points at `User` through `granted_by`, so the join
        # columns have to be named explicitly.
        through_fields=("user", "role"),
        related_name="users",
        blank=True,
        verbose_name=_("roles"),
    )

    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(
        _("django admin access"),
        default=False,
        help_text=_("Grants access to the emergency Django admin, not the merchant dashboard."),
    )
    is_verified = models.BooleanField(_("email verified"), default=False)
    verified_at = models.DateTimeField(_("verified at"), null=True, blank=True)

    accepted_terms_at = models.DateTimeField(_("accepted terms at"), null=True, blank=True)
    marketing_opt_in = models.BooleanField(_("accepts marketing"), default=False)

    anonymized_at = models.DateTimeField(_("anonymised at"), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]
        constraints = [
            # The same email may exist once per tenant, plus once with no tenant
            # (platform administrators). Postgres treats NULLs as distinct, which
            # is why platform accounts get their own partial constraint.
            models.UniqueConstraint(
                fields=["tenant", "email"],
                name="uniq_user_tenant_email",
                condition=models.Q(tenant__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["email"],
                name="uniq_platform_user_email",
                condition=models.Q(tenant__isnull=True),
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "user_type"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.email

    # --- Naming --------------------------------------------------------------
    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    # --- Authorization -------------------------------------------------------
    @property
    def is_platform_admin(self) -> bool:
        """Operates above tenants; bypasses tenant permission checks."""
        return self.is_superuser or self.user_type == UserType.PLATFORM_ADMIN

    @property
    def is_customer(self) -> bool:
        return self.user_type == UserType.CUSTOMER

    @property
    def is_merchant_user(self) -> bool:
        return self.user_type in {UserType.STAFF, UserType.MANAGER, UserType.ADMINISTRATOR}

    def permission_codes(self) -> set[str]:
        """Every permission code this account holds, cached per instance.

        Cached because a single request checks permissions many times, and each
        check would otherwise cost a join across roles.
        """
        cached = getattr(self, "_permission_codes_cache", None)
        if cached is not None:
            return cached

        if self.is_platform_admin or self.user_type == UserType.ADMINISTRATOR:
            codes = set(ALL_PERMISSION_CODES)
        else:
            codes = set(Permission.objects.filter(roles__users=self).values_list("code", flat=True))

        self._permission_codes_cache = codes
        return codes

    def has_permission_code(self, code: str) -> bool:
        """Whether this account may perform ``code``.

        Unknown codes always deny: a typo in a view must fail closed.
        """
        if code not in PERMISSION_CATALOGUE:
            return False
        if not self.is_active:
            return False
        return code in self.permission_codes()

    def refresh_permission_cache(self) -> None:
        self._permission_codes_cache = None


class UserRole(BaseModel):
    """Assignment of a role to a user, with provenance for the audit trail."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="granted_roles"
    )

    class Meta:
        verbose_name = _("user role")
        verbose_name_plural = _("user roles")
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role"),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.user} → {self.role}"


class AuthTokenQuerySet(models.QuerySet):
    def valid(self) -> AuthTokenQuerySet:
        return self.filter(used_at__isnull=True, expires_at__gt=timezone.now())


class AuthToken(BaseModel):
    """Single-use token for email verification and password reset.

    Only the SHA-256 digest is persisted; the plaintext exists just long enough
    to be emailed. Verification therefore hashes the incoming value and looks
    the digest up — a database dump yields nothing usable.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_tokens")
    purpose = models.CharField(_("purpose"), max_length=32, choices=TokenPurpose.choices)
    token_hash = models.CharField(_("token hash"), max_length=64, db_index=True)
    expires_at = models.DateTimeField(_("expires at"), db_index=True)
    used_at = models.DateTimeField(_("used at"), null=True, blank=True)
    requested_ip = models.GenericIPAddressField(_("requested from"), null=True, blank=True)

    objects = AuthTokenQuerySet.as_manager()

    class Meta:
        verbose_name = _("authentication token")
        verbose_name_plural = _("authentication tokens")
        indexes = [models.Index(fields=["purpose", "token_hash"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.purpose} for {self.user_id}"

    # --- Token helpers -------------------------------------------------------
    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def issue(
        cls,
        *,
        user: User,
        purpose: str,
        ttl_hours: int,
        ip: str | None = None,
    ) -> tuple[AuthToken, str]:
        """Create a token, invalidating any outstanding one for that purpose.

        Returns the record and the plaintext value to embed in the email.
        """
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            purpose=purpose,
            token_hash=cls.hash_token(raw),
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
            requested_ip=ip,
        )
        return token, raw

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "updated_at"])


class LoginAttempt(BaseModel):
    """Record of a sign-in attempt, used for lockout and incident review.

    Only the email, outcome and origin are kept — never the submitted password.
    """

    email = models.EmailField(_("email"), db_index=True)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    successful = models.BooleanField(_("successful"), default=False)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=255, blank=True)
    failure_reason = models.CharField(_("failure reason"), max_length=64, blank=True)

    class Meta:
        verbose_name = _("login attempt")
        verbose_name_plural = _("login attempts")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "created_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.email} {'ok' if self.successful else 'failed'}"


class Address(TenantOwnedModel):
    """A customer delivery address.

    Addresses are personal data: they are only ever exposed to their owner and
    to staff holding ``customers.view`` (spec §21, LGPD).
    """

    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(_("label"), max_length=60, blank=True)
    recipient_name = models.CharField(_("recipient"), max_length=160)
    postal_code = models.CharField(_("postal code"), max_length=16)
    street = models.CharField(_("street"), max_length=255)
    number = models.CharField(_("number"), max_length=32)
    complement = models.CharField(_("complement"), max_length=120, blank=True)
    neighborhood = models.CharField(_("neighborhood"), max_length=120)
    city = models.CharField(_("city"), max_length=120)
    state = models.CharField(_("state"), max_length=64)
    country = models.CharField(_("country"), max_length=2, default="BR")
    reference = models.CharField(_("reference point"), max_length=255, blank=True)
    latitude = models.DecimalField(
        _("latitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        _("longitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_default = models.BooleanField(_("default address"), default=False)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "-created_at"]
        indexes = [models.Index(fields=["customer", "is_default"])]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.street}, {self.number} — {self.city}"

    def as_snapshot(self) -> dict[str, Any]:
        """Flatten to the immutable copy stored on an order.

        Orders keep their own copy so editing an address later never rewrites
        where a past delivery actually went.
        """
        return {
            "recipient_name": self.recipient_name,
            "postal_code": self.postal_code,
            "street": self.street,
            "number": self.number,
            "complement": self.complement,
            "neighborhood": self.neighborhood,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "reference": self.reference,
            "latitude": str(self.latitude) if self.latitude is not None else None,
            "longitude": str(self.longitude) if self.longitude is not None else None,
        }
