"""
The permission catalogue.

Authorization is code-based, not role-based (spec §7). Roles are merchant-
editable bundles of these codes; the application only ever asks "does this actor
hold ``orders.refund``?". Adding a capability means adding a code here and
seeding it — never inventing a new role name inside a view.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class UserType(models.TextChoices):
    """Coarse account category.

    Fine-grained capability always comes from permission codes; this field
    exists for defaults, UI grouping and the "is this a shopper?" question.
    """

    CUSTOMER = "CUSTOMER", _("Customer")
    STAFF = "STAFF", _("Staff")
    MANAGER = "MANAGER", _("Manager")
    ADMINISTRATOR = "ADMINISTRATOR", _("Administrator")
    PLATFORM_ADMIN = "PLATFORM_ADMIN", _("Platform administrator")


#: ``code -> human description``. The single source of truth for what the
#: platform can authorise.
PERMISSION_CATALOGUE: dict[str, str] = {
    # Catalog
    "catalog.view": "View products, categories and brands",
    "catalog.create": "Create catalog entries",
    "catalog.update": "Update catalog entries",
    "catalog.delete": "Delete or archive catalog entries",
    # Inventory
    "inventory.view": "View stock levels and movements",
    "inventory.adjust": "Adjust stock quantities",
    "inventory.manage": "Configure inventory rules",
    # Pricing
    "pricing.view": "View prices, costs and margins",
    "pricing.create": "Create prices and scheduled prices",
    "pricing.update": "Change prices",
    # Promotions
    "promotions.view": "View promotions and coupons",
    "promotions.manage": "Create and edit promotions and coupons",
    # Orders
    "orders.view": "View orders",
    "orders.update": "Advance order status",
    "orders.cancel": "Cancel orders",
    "orders.refund": "Refund orders",
    # Customers
    "customers.view": "View customer records",
    "customers.update": "Edit customer records",
    # Payments
    "payments.view": "View payments",
    "payments.refund": "Issue refunds",
    # Reports and finance
    "reports.view": "View reports and dashboards",
    "reports.export": "Export reports",
    "finance.view": "View financial records",
    "finance.manage": "Create and edit financial records",
    # Users and tenant
    "users.view": "View platform users",
    "users.manage": "Invite, edit and deactivate users",
    "tenant.settings": "Change store settings",
    "tenant.branding": "Change store branding",
    # Documents and media
    "documents.view": "View documents",
    "documents.upload": "Upload documents",
    "documents.delete": "Delete documents",
    "media.upload": "Upload images and banners",
    # Audit
    "audit.view": "Read the audit log",
    # System
    #
    # Deliberately a *capability*, not a page code. Page codes are
    # hierarchical, so anything under `perm.admin` is granted to every
    # holder of `perm.admin` — which is exactly what must not happen to a
    # screen that reports queue depth, storage state and configuration.
    "system.diagnostics": "Read system health and diagnostics",
}

#: Prefix marking a *page access* permission, as opposed to a capability.
#:
#: Capability codes above answer "may this actor refund an order?". Page codes
#: answer "may this actor open this screen?". They are separate questions: a
#: manager may hold `orders.refund` yet have no reason to reach the finance
#: dashboard.
PAGE_PERMISSION_PREFIX = "perm"

#: Page-access permissions. **Hierarchical**: holding a parent grants every
#: descendant, so `perm.admin` opens the whole dashboard while
#: `perm.admin.profile` opens only that screen (see
#: :meth:`apps.accounts.models.User.has_permission_code`).
PAGE_PERMISSIONS: dict[str, str] = {
    "perm.admin": "Open the merchant dashboard",
    "perm.admin.dashboard": "Open the dashboard overview",
    "perm.admin.products": "Open product management",
    "perm.admin.orders": "Open order management",
    "perm.admin.inventory": "Open inventory management",
    "perm.admin.customers": "Open the customer list",
    "perm.admin.users": "Open user and role management",
    "perm.admin.finance": "Open the finance area",
    "perm.admin.reports": "Open reports",
    "perm.admin.promotions": "Open promotions",
    "perm.admin.settings": "Open store settings",
    "perm.admin.audit": "Open the audit log",
    "perm.admin.diagnostics": "Open system diagnostics",
    "perm.account": "Open the customer account area",
    "perm.account.profile": "Open the profile page",
    "perm.account.addresses": "Open saved addresses",
    "perm.account.orders": "Open personal order history",
    "perm.account.lists": "Open shopping lists",
}

PERMISSION_CATALOGUE.update(PAGE_PERMISSIONS)

ALL_PERMISSION_CODES: tuple[str, ...] = tuple(PERMISSION_CATALOGUE)

#: Page codes every signed-in customer holds without an explicit grant. Their
#: own profile is not a privilege that needs administering.
DEFAULT_CUSTOMER_PERMISSIONS: tuple[str, ...] = ("perm.account",)


def is_page_permission(code: str) -> bool:
    return code == PAGE_PERMISSION_PREFIX or code.startswith(f"{PAGE_PERMISSION_PREFIX}.")


def permission_ancestors(code: str) -> tuple[str, ...]:
    """Return ``code`` and every parent that would also grant it.

    ``perm.admin.users`` yields ``("perm.admin.users", "perm.admin", "perm")``.
    Capability codes have no hierarchy — holding ``catalog`` is not a thing —
    so they yield only themselves.
    """
    if not is_page_permission(code):
        return (code,)

    parts = code.split(".")
    return tuple(".".join(parts[: index + 1]) for index in range(len(parts)))[::-1]


class SystemRole(models.TextChoices):
    """Roles created for every tenant. Merchants may add their own."""

    STAFF = "staff", _("Staff")
    MANAGER = "manager", _("Manager")
    ADMINISTRATOR = "administrator", _("Administrator")


#: Default code bundles for the system roles. Merchants can edit the resulting
#: role rows; these are only the starting point.
SYSTEM_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    SystemRole.STAFF: (
        "catalog.view",
        "inventory.view",
        "inventory.adjust",
        "orders.view",
        "orders.update",
        "customers.view",
        "payments.view",
        "pricing.view",
        "promotions.view",
        "documents.view",
        # Specific pages only. The bare `perm.admin` parent would grant every
        # dashboard screen by hierarchy, including finance and user management.
        "perm.admin.dashboard",
        "perm.admin.orders",
        "perm.admin.products",
        "perm.admin.inventory",
        "perm.admin.customers",
        "perm.account",
    ),
    SystemRole.MANAGER: (
        "catalog.view",
        "catalog.create",
        "catalog.update",
        "inventory.view",
        "inventory.adjust",
        "inventory.manage",
        "pricing.view",
        "pricing.create",
        "pricing.update",
        "promotions.view",
        "promotions.manage",
        "orders.view",
        "orders.update",
        "orders.cancel",
        "customers.view",
        "customers.update",
        "payments.view",
        "reports.view",
        "reports.export",
        "documents.view",
        "documents.upload",
        "media.upload",
        # Managers reach every dashboard screen except users and settings, so
        # the pages are listed individually rather than granting the parent.
        "perm.admin.dashboard",
        "perm.admin.products",
        "perm.admin.orders",
        "perm.admin.inventory",
        "perm.admin.customers",
        "perm.admin.reports",
        "perm.admin.promotions",
        "perm.account",
    ),
    # Administrators get everything defined in the catalogue; listing the codes
    # explicitly would mean a new permission is silently withheld from them.
    SystemRole.ADMINISTRATOR: ALL_PERMISSION_CODES,
}


class TokenPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION", _("Email verification")
    PASSWORD_RESET = "PASSWORD_RESET", _("Password reset")


#: Single-use token lifetimes. Short enough to limit exposure from a leaked
#: mailbox, long enough that a customer can act on the email.
EMAIL_VERIFICATION_TTL_HOURS = 48
PASSWORD_RESET_TTL_HOURS = 2
