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
}

ALL_PERMISSION_CODES: tuple[str, ...] = tuple(PERMISSION_CATALOGUE)


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
