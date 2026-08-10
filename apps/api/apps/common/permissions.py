"""
Authorization primitives.

Authorization is expressed with *permission codes* (``catalog.update``), never
with role names. Roles are a packaging detail that merchants reconfigure;
permission codes are what the code depends on (spec §7).

Views declare what they need::

    class ProductViewSet(TenantModelViewSet):
        required_permissions = {
            "list": ["catalog.view"],
            "create": ["catalog.create"],
            "default": ["catalog.view"],
        }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework.permissions import SAFE_METHODS, BasePermission

if TYPE_CHECKING:  # pragma: no cover
    from rest_framework.request import Request
    from rest_framework.views import APIView


def _required_for(view: APIView) -> list[str]:
    """Read the permission codes a view action needs."""
    declared = getattr(view, "required_permissions", None)
    if not declared:
        return []
    if isinstance(declared, list | tuple | set):
        return list(declared)
    action = getattr(view, "action", None) or ""
    return list(declared.get(action) or declared.get("default") or [])


class IsAuthenticatedCustomer(BasePermission):
    """Any verified, active, authenticated account."""

    message = "Authentication is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)


class HasTenantPermission(BasePermission):
    """Checks the view's declared permission codes against the actor's roles.

    Platform administrators bypass the check because they operate above any
    single tenant; every other actor must hold the code inside the resolved
    tenant.
    """

    message = "You do not have permission to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False

        required = _required_for(view)
        if not required:
            return True

        if getattr(user, "is_platform_admin", False):
            return True

        return all(user.has_permission_code(code) for code in required)

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        """Object access additionally requires the object to be in-tenant."""
        tenant_id = getattr(request, "tenant_id", None)
        obj_tenant_id = getattr(obj, "tenant_id", None)
        if obj_tenant_id is None or tenant_id is None:
            return True
        return obj_tenant_id == tenant_id


class IsOwnerOrHasPermission(BasePermission):
    """Customers reach their own records; staff need the declared codes.

    Used for orders, addresses and favourites, where the same endpoint serves
    both the customer who created the record and the merchant's staff.
    """

    message = "You do not have permission to access this resource."
    owner_field = "customer_id"

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False

        owner_field = getattr(view, "owner_field", self.owner_field)
        if getattr(obj, owner_field, None) == user.pk:
            return True

        if getattr(user, "is_platform_admin", False):
            return True

        required = _required_for(view)
        if not required:
            return False
        return all(user.has_permission_code(code) for code in required)


class ReadOnlyOrHasPermission(HasTenantPermission):
    """Anonymous reads, authorised writes.

    The storefront catalog is public; changing it is not.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return super().has_permission(request, view)
