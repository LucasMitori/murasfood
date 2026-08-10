"""
Account business operations.

Views stay thin; everything with a rule attached lives here (spec §4).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.exceptions import DomainError, NotFoundError

from .constants import (
    EMAIL_VERIFICATION_TTL_HOURS,
    PASSWORD_RESET_TTL_HOURS,
    PERMISSION_CATALOGUE,
    SYSTEM_ROLE_PERMISSIONS,
    SystemRole,
    TokenPurpose,
    UserType,
)
from .models import Address, AuthToken, LoginAttempt, Permission, Role, User, UserRole

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.accounts")


class InvalidTokenError(DomainError):
    default_detail = _("This link is invalid or has expired.")
    default_code = "INVALID_TOKEN"


class AccountLockedError(DomainError):
    default_detail = _("Too many failed attempts. Try again later.")
    default_code = "ACCOUNT_LOCKED"
    status_code = 429


class EmailAlreadyRegisteredError(DomainError):
    default_detail = _("An account already exists for this email address.")
    default_code = "EMAIL_ALREADY_REGISTERED"


# =============================================================================
# Permission and role provisioning
# =============================================================================
def sync_permissions() -> int:
    """Make the ``Permission`` table match :data:`PERMISSION_CATALOGUE`.

    Idempotent, so it can run on every deploy. Codes removed from the catalogue
    are left in place: dropping them would silently revoke access from custom
    merchant roles that still reference them.
    """
    existing = dict(Permission.objects.values_list("code", "description"))
    to_create = [
        Permission(code=code, description=description)
        for code, description in PERMISSION_CATALOGUE.items()
        if code not in existing
    ]
    Permission.objects.bulk_create(to_create, ignore_conflicts=True)

    to_update = [
        Permission(id=perm.id, code=perm.code, description=PERMISSION_CATALOGUE[perm.code])
        for perm in Permission.objects.filter(code__in=PERMISSION_CATALOGUE)
        if existing.get(perm.code) != PERMISSION_CATALOGUE[perm.code]
    ]
    if to_update:
        Permission.objects.bulk_update(to_update, ["description"])

    return len(to_create)


@transaction.atomic
def ensure_system_roles(tenant: Tenant) -> dict[str, Role]:
    """Create (or repair) the standard roles for a tenant."""
    sync_permissions()
    permissions_by_code = {p.code: p for p in Permission.objects.all()}

    roles: dict[str, Role] = {}
    for slug, codes in SYSTEM_ROLE_PERMISSIONS.items():
        role, _created = Role.objects.get_or_create(
            tenant=tenant,
            slug=slug,
            defaults={
                "name": str(SystemRole(slug).label),
                "is_system": True,
                "description": f"Default {SystemRole(slug).label.lower()} role",
            },
        )
        role.permissions.set([permissions_by_code[c] for c in codes if c in permissions_by_code])
        roles[slug] = role
    return roles


def assign_role(user: User, role: Role, *, granted_by: User | None = None) -> UserRole:
    """Grant a role, refreshing the user's cached permission set."""
    assignment, _ = UserRole.objects.get_or_create(
        user=user, role=role, defaults={"granted_by": granted_by}
    )
    user.refresh_permission_cache()
    return assignment


# =============================================================================
# Registration and verification
# =============================================================================
@transaction.atomic
def register_customer(
    *,
    tenant: Tenant,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    marketing_opt_in: bool = False,
    accepted_terms: bool = False,
    ip: str | None = None,
) -> tuple[User, str]:
    """Create a shopper account and issue an email-verification token.

    Returns the user and the plaintext verification token. The token is handed
    to the notification layer and then forgotten — only its hash is stored.
    """
    email = email.strip().lower()
    if User.objects.filter(tenant=tenant, email=email).exists():
        raise EmailAlreadyRegisteredError()

    validate_password(password)

    user = User.objects.create_user(
        email=email,
        password=password,
        tenant=tenant,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
        user_type=UserType.CUSTOMER,
        marketing_opt_in=marketing_opt_in,
        accepted_terms_at=timezone.now() if accepted_terms else None,
    )

    _token, raw = AuthToken.issue(
        user=user,
        purpose=TokenPurpose.EMAIL_VERIFICATION,
        ttl_hours=EMAIL_VERIFICATION_TTL_HOURS,
        ip=ip,
    )
    send_verification_email(user, raw)
    return user, raw


def verification_url(user: User, raw_token: str) -> str:
    """Build the storefront link a customer clicks to verify their address."""
    return f"{settings.PUBLIC_APP_URL}/auth/verify-email?token={quote(raw_token)}&uid={user.pk}"


def password_reset_url(user: User, raw_token: str) -> str:
    return f"{settings.PUBLIC_APP_URL}/auth/reset-password?token={quote(raw_token)}&uid={user.pk}"


def send_verification_email(user: User, raw_token: str) -> None:
    """Queue the double opt-in email."""
    from apps.notifications.services import queue_transactional_email

    queue_transactional_email(
        tenant=user.tenant,
        template_key="account.verify",
        recipient=user.email,
        context={
            "first_name": user.get_short_name(),
            "verification_url": verification_url(user, raw_token),
            "expires_in_hours": EMAIL_VERIFICATION_TTL_HOURS,
        },
        user=user,
    )


@transaction.atomic
def verify_email(*, raw_token: str, user_id: Any | None = None) -> User:
    """Consume a verification token and mark the address as verified."""
    token = (
        AuthToken.objects.select_related("user")
        .filter(
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=AuthToken.hash_token(raw_token),
        )
        .first()
    )
    if token is None or not token.is_valid:
        raise InvalidTokenError()
    if user_id is not None and str(token.user_id) != str(user_id):
        raise InvalidTokenError()

    token.consume()
    user = token.user
    if not user.is_verified:
        user.is_verified = True
        user.verified_at = timezone.now()
        user.save(update_fields=["is_verified", "verified_at", "updated_at"])

        from apps.notifications.services import queue_transactional_email

        queue_transactional_email(
            tenant=user.tenant,
            template_key="account.welcome",
            recipient=user.email,
            context={"first_name": user.get_short_name()},
            user=user,
        )
    return user


def resend_verification(*, tenant: Tenant, email: str, ip: str | None = None) -> None:
    """Re-issue a verification email.

    Deliberately silent about whether the address exists — an enumeration oracle
    on this endpoint would leak the customer list.
    """
    user = User.objects.filter(tenant=tenant, email=email.strip().lower()).first()
    if user is None or user.is_verified:
        return
    _token, raw = AuthToken.issue(
        user=user,
        purpose=TokenPurpose.EMAIL_VERIFICATION,
        ttl_hours=EMAIL_VERIFICATION_TTL_HOURS,
        ip=ip,
    )
    send_verification_email(user, raw)


# =============================================================================
# Password reset
# =============================================================================
def request_password_reset(*, tenant: Tenant, email: str, ip: str | None = None) -> None:
    """Send a reset link. Always succeeds from the caller's point of view."""
    user = User.objects.filter(tenant=tenant, email=email.strip().lower(), is_active=True).first()
    if user is None:
        logger.info("password_reset_requested_unknown_email", extra={"event": "auth.reset.unknown"})
        return

    _token, raw = AuthToken.issue(
        user=user, purpose=TokenPurpose.PASSWORD_RESET, ttl_hours=PASSWORD_RESET_TTL_HOURS, ip=ip
    )

    from apps.notifications.services import queue_transactional_email

    queue_transactional_email(
        tenant=user.tenant,
        template_key="account.password_reset",
        recipient=user.email,
        context={
            "first_name": user.get_short_name(),
            "reset_url": password_reset_url(user, raw),
            "expires_in_hours": PASSWORD_RESET_TTL_HOURS,
        },
        user=user,
    )


@transaction.atomic
def reset_password(*, raw_token: str, new_password: str, user_id: Any | None = None) -> User:
    """Consume a reset token and set a new password.

    Every outstanding session is revoked afterwards: a password reset is how a
    user recovers from a compromise, so old refresh tokens must stop working.
    """
    token = (
        AuthToken.objects.select_related("user")
        .filter(purpose=TokenPurpose.PASSWORD_RESET, token_hash=AuthToken.hash_token(raw_token))
        .first()
    )
    if token is None or not token.is_valid:
        raise InvalidTokenError()
    if user_id is not None and str(token.user_id) != str(user_id):
        raise InvalidTokenError()

    user = token.user
    validate_password(new_password, user=user)

    token.consume()
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)
    return user


def change_password(*, user: User, current_password: str, new_password: str) -> None:
    """Change a password for a signed-in user."""
    if not user.check_password(current_password):
        raise DomainError(_("The current password is incorrect."), code="INVALID_CREDENTIALS")
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)


def revoke_all_refresh_tokens(user: User) -> int:
    """Blacklist every outstanding refresh token for a user."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    revoked = 0
    for outstanding in OutstandingToken.objects.filter(user=user):
        _obj, created = BlacklistedToken.objects.get_or_create(token=outstanding)
        revoked += int(created)
    return revoked


# =============================================================================
# Login protection
# =============================================================================
def record_login_attempt(
    *,
    email: str,
    tenant: Tenant | None,
    successful: bool,
    ip: str | None = None,
    user_agent: str = "",
    failure_reason: str = "",
) -> None:
    LoginAttempt.objects.create(
        email=email.strip().lower(),
        tenant=tenant,
        successful=successful,
        ip_address=ip,
        user_agent=user_agent[:255],
        failure_reason=failure_reason[:64],
    )
    if not successful:
        logger.warning(
            "login_failed",
            extra={"event": "auth.login.failed", "email_domain": email.split("@")[-1]},
        )


def is_locked_out(*, email: str, tenant: Tenant | None) -> bool:
    """Whether recent failures should block another attempt.

    Counted per email within a sliding window. Successful logins reset the
    window because the counter only looks at attempts newer than the last
    success.
    """
    window_start = timezone.now() - timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    attempts = LoginAttempt.objects.filter(
        email=email.strip().lower(), tenant=tenant, created_at__gte=window_start
    ).order_by("-created_at")[: settings.LOGIN_MAX_FAILED_ATTEMPTS]

    attempts = list(attempts)
    if len(attempts) < settings.LOGIN_MAX_FAILED_ATTEMPTS:
        return False
    return all(not attempt.successful for attempt in attempts)


# =============================================================================
# Addresses
# =============================================================================
@transaction.atomic
def set_default_address(*, customer: User, address: Address) -> Address:
    """Promote one address to default, demoting the others atomically."""
    if address.customer_id != customer.pk:
        raise NotFoundError()
    Address.objects.filter(customer=customer).exclude(pk=address.pk).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default", "updated_at"])
    return address


@transaction.atomic
def create_address(*, customer: User, tenant: Tenant, **fields: Any) -> Address:
    """Create an address; the first one a customer saves becomes the default."""
    make_default = (
        fields.pop("is_default", False) or not Address.objects.filter(customer=customer).exists()
    )
    address = Address.objects.create(customer=customer, tenant=tenant, **fields)
    if make_default:
        set_default_address(customer=customer, address=address)
    return address


# =============================================================================
# LGPD
# =============================================================================
@transaction.atomic
def anonymize_user(user: User, *, reason: str = "user_request") -> User:
    """Scrub personal data while preserving financial history.

    Orders must keep their totals, taxes and payment records — deleting them
    would corrupt accounting (invariant #9). What we can remove is the link to a
    living person: name, email, phone and addresses.
    """
    stamp = timezone.now()
    user.email = f"anonymized+{user.pk.hex}@invalid.local"
    user.first_name = ""
    user.last_name = ""
    user.phone = ""
    user.is_active = False
    user.marketing_opt_in = False
    user.anonymized_at = stamp
    user.set_unusable_password()
    user.save()

    Address.objects.filter(customer=user).delete()
    AuthToken.objects.filter(user=user, used_at__isnull=True).update(used_at=stamp)
    revoke_all_refresh_tokens(user)

    logger.info("account_anonymized", extra={"event": "lgpd.anonymize", "reason": reason})
    return user


def export_personal_data(user: User) -> dict[str, Any]:
    """Everything the platform holds about one person, for an LGPD request."""
    from apps.orders.models import Order

    return {
        "account": {
            "id": str(user.pk),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "created_at": user.created_at.isoformat(),
            "verified": user.is_verified,
            "marketing_opt_in": user.marketing_opt_in,
        },
        "addresses": [
            {**address.as_snapshot(), "label": address.label}
            for address in Address.objects.filter(customer=user)
        ],
        "orders": [
            {
                "number": order.number,
                "status": order.status,
                "total": str(order.total),
                "created_at": order.created_at.isoformat(),
            }
            for order in Order.objects.filter(customer=user).order_by("-created_at")
        ],
    }


# =============================================================================
# Permission and role assignment
# =============================================================================
@transaction.atomic
def replace_direct_permissions(
    *, user: User, codes: list[str], granted_by: User | None = None
) -> list[str]:
    """Set the account's direct grants to exactly ``codes``.

    Only *direct* grants are touched. Anything the account holds through a role
    is unaffected, which is what lets the editor present the two as separate
    lists without one silently clobbering the other.

    Unknown codes are ignored rather than rejected: the catalogue can shrink
    between a page load and a save, and failing the whole request over a stale
    checkbox would be worse than dropping it.

    Returns the codes actually stored, sorted.
    """
    from .models import Permission, UserPermission

    wanted = {code for code in codes if code in PERMISSION_CATALOGUE}
    permissions = {p.code: p for p in Permission.objects.filter(code__in=wanted)}

    UserPermission.objects.filter(user=user).exclude(permission__code__in=wanted).delete()

    existing = set(
        UserPermission.objects.filter(user=user).values_list("permission__code", flat=True)
    )
    UserPermission.objects.bulk_create(
        [
            UserPermission(user=user, permission=permissions[code], granted_by=granted_by)
            for code in wanted - existing
            if code in permissions
        ],
        ignore_conflicts=True,
    )

    user.refresh_permission_cache()
    logger.info(
        "user_permissions_replaced",
        extra={"event": "accounts.permissions_replaced", "count": len(wanted)},
    )
    return sorted(wanted)


@transaction.atomic
def replace_roles(*, user: User, slugs: list[str], granted_by: User | None = None) -> list[str]:
    """Set the account's roles to exactly ``slugs`` within its own tenant.

    Roles from another tenant are ignored: assigning one would be a cross-tenant
    privilege escalation (invariant #1).
    """
    from .models import Role

    roles = {
        role.slug: role for role in Role.objects.filter(tenant_id=user.tenant_id, slug__in=slugs)
    }

    UserRole.objects.filter(user=user).exclude(role__slug__in=roles).delete()

    existing = set(UserRole.objects.filter(user=user).values_list("role__slug", flat=True))
    for slug, role in roles.items():
        if slug not in existing:
            UserRole.objects.get_or_create(
                user=user, role=role, defaults={"granted_by": granted_by}
            )

    user.refresh_permission_cache()
    return sorted(roles)
