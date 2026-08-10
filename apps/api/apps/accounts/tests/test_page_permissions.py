"""
Hierarchical page permissions and direct grants.

Two mechanisms are covered here:

* **Page permissions** (`perm.*`) are hierarchical — holding a parent grants
  every descendant, so `perm.admin` opens the whole dashboard.
* **Direct grants** sit alongside roles; effective access is the union of the
  two, and revoking a direct grant must not touch what a role provides.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.constants import (
    PAGE_PERMISSIONS,
    PERMISSION_CATALOGUE,
    is_page_permission,
    permission_ancestors,
)
from apps.accounts.models import Permission, UserPermission

pytestmark = pytest.mark.django_db


class TestHierarchyHelpers:
    def test_page_codes_are_recognised(self) -> None:
        assert is_page_permission("perm.admin") is True
        assert is_page_permission("perm.admin.users") is True
        assert is_page_permission("catalog.view") is False

    def test_ancestors_run_from_specific_to_general(self) -> None:
        assert permission_ancestors("perm.admin.users") == (
            "perm.admin.users",
            "perm.admin",
            "perm",
        )

    def test_capability_codes_have_no_hierarchy(self) -> None:
        # Holding "catalog" is not a thing; only the exact code grants it.
        assert permission_ancestors("catalog.view") == ("catalog.view",)

    def test_every_page_code_is_in_the_catalogue(self) -> None:
        for code in PAGE_PERMISSIONS:
            assert code in PERMISSION_CATALOGUE


class TestHierarchicalChecks:
    def test_a_parent_grants_its_children(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("perm.admin")

        assert customer.has_permission_code("perm.admin") is True
        assert customer.has_permission_code("perm.admin.users") is True
        assert customer.has_permission_code("perm.admin.finance") is True

    def test_a_child_does_not_grant_its_parent(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("perm.admin.orders")

        assert customer.has_permission_code("perm.admin.orders") is True
        # Access to one screen is not access to the dashboard at large.
        assert customer.has_permission_code("perm.admin") is False
        assert customer.has_permission_code("perm.admin.finance") is False

    def test_hierarchy_does_not_leak_into_capabilities(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("perm.admin")

        # A page grant must never imply the ability to act.
        assert customer.has_permission_code("orders.refund") is False
        assert customer.has_permission_code("catalog.delete") is False

    def test_unknown_codes_fail_closed(self, admin_user: Any) -> None:
        assert admin_user.has_permission_code("perm.admin.nonexistent") is False

    def test_administrators_hold_every_page(self, admin_user: Any) -> None:
        for code in PAGE_PERMISSIONS:
            assert admin_user.has_permission_code(code) is True


class TestDirectGrants:
    def test_grant_and_revoke(self, tenant: Any, customer: Any) -> None:
        assert customer.has_permission_code("reports.view") is False

        customer.grant_permission("reports.view")
        assert customer.has_permission_code("reports.view") is True

        customer.revoke_permission("reports.view")
        assert customer.has_permission_code("reports.view") is False

    def test_granting_twice_is_idempotent(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("reports.view")
        customer.grant_permission("reports.view")

        assert UserPermission.objects.filter(user=customer).count() == 1

    def test_granting_an_unknown_code_is_a_no_op(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("not.a.real.code")
        assert UserPermission.objects.filter(user=customer).count() == 0

    def test_effective_permissions_are_roles_plus_direct(
        self, tenant: Any, staff_user: Any
    ) -> None:
        assert staff_user.has_permission_code("orders.view") is True  # from the staff role
        assert staff_user.has_permission_code("finance.view") is False

        staff_user.grant_permission("finance.view")

        assert staff_user.has_permission_code("orders.view") is True
        assert staff_user.has_permission_code("finance.view") is True

    def test_revoking_does_not_remove_what_a_role_grants(
        self, tenant: Any, staff_user: Any
    ) -> None:
        # `orders.view` comes from the staff role, not a direct grant.
        staff_user.revoke_permission("orders.view")

        assert staff_user.has_permission_code("orders.view") is True

    def test_the_two_sources_are_reported_separately(self, tenant: Any, staff_user: Any) -> None:
        """The admin UI must show which grants it can actually revoke."""
        staff_user.grant_permission("finance.view")

        assert "finance.view" in staff_user.direct_permission_codes()
        assert "finance.view" not in staff_user.role_permission_codes()
        assert "orders.view" in staff_user.role_permission_codes()
        assert "orders.view" not in staff_user.direct_permission_codes()

    def test_a_deactivated_account_holds_nothing(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("perm.admin")
        customer.is_active = False

        assert customer.has_permission_code("perm.admin") is False


class TestRoleBundles:
    def test_staff_reach_their_screens_but_not_finance(self, staff_user: Any) -> None:
        """Staff hold individual pages, never the `perm.admin` parent.

        Granting the parent to get them past the area gate would hand them
        finance and user management too, by hierarchy.
        """
        assert staff_user.has_permission_code("perm.admin") is False
        assert staff_user.has_permission_code("perm.admin.orders") is True
        assert staff_user.has_permission_code("perm.admin.products") is True
        assert staff_user.has_permission_code("perm.admin.finance") is False
        assert staff_user.has_permission_code("perm.admin.users") is False

    def test_managers_reach_reports_but_not_user_management(self, tenant: Any) -> None:
        from apps.accounts.constants import SystemRole, UserType
        from apps.accounts.models import Role, User
        from apps.accounts.services import assign_role

        manager = User.objects.create_user(
            email="gerente@example.test",
            password="senha-super-secreta-9",
            tenant=tenant,
            user_type=UserType.MANAGER,
        )
        assign_role(manager, Role.objects.get(tenant=tenant, slug=SystemRole.MANAGER))

        assert manager.has_permission_code("perm.admin.reports") is True
        assert manager.has_permission_code("perm.admin.promotions") is True
        assert manager.has_permission_code("perm.admin.users") is False
        assert manager.has_permission_code("perm.admin.settings") is False

    def test_customers_reach_only_their_own_area(self, customer: Any) -> None:
        assert customer.has_permission_code("perm.account.profile") is True
        assert customer.has_permission_code("perm.admin") is False


class TestPermissionsEndpoint:
    def test_lists_the_catalogue_for_authorised_staff(self, admin_client_api: APIClient) -> None:
        response = admin_client_api.get("/api/v1/admin/permissions/")

        assert response.status_code == 200
        codes = {row["code"] for row in response.data}
        assert "orders.refund" in codes
        assert "perm.admin.users" in codes

    def test_groups_pages_separately_from_capabilities(self, admin_client_api: APIClient) -> None:
        response = admin_client_api.get("/api/v1/admin/permissions/")

        by_code = {row["code"]: row for row in response.data}
        assert by_code["perm.admin"]["is_page"] is True
        assert by_code["orders.refund"]["is_page"] is False

    def test_requires_permission(self, customer_client: APIClient) -> None:
        assert customer_client.get("/api/v1/admin/permissions/").status_code == 403

    def test_every_catalogue_code_is_seeded(self, tenant: Any) -> None:
        stored = set(Permission.objects.values_list("code", flat=True))
        assert set(PERMISSION_CATALOGUE).issubset(stored)


class TestAdminAreaGate:
    """`can_access_admin` is the area gate, distinct from `perm.admin`.

    A staff member holding only `perm.admin.orders` must reach that one screen;
    granting them `perm.admin` to get past the gate would hand them finance and
    user management by hierarchy.
    """

    def test_staff_pass_the_gate_without_holding_the_parent(self, staff_user: Any) -> None:
        assert staff_user.can_access_admin() is True
        assert staff_user.has_permission_code("perm.admin") is False

    def test_customers_do_not_pass(self, customer: Any) -> None:
        assert customer.can_access_admin() is False

    def test_administrators_pass(self, admin_user: Any) -> None:
        assert admin_user.can_access_admin() is True

    def test_deactivated_accounts_do_not_pass(self, staff_user: Any) -> None:
        staff_user.is_active = False
        assert staff_user.can_access_admin() is False

    def test_accessible_pages_expands_the_hierarchy(self, tenant: Any, customer: Any) -> None:
        customer.grant_permission("perm.admin")
        pages = customer.accessible_pages()

        assert "perm.admin" in pages
        assert "perm.admin.users" in pages
        assert "perm.admin.finance" in pages

    def test_accessible_pages_stays_narrow_for_staff(self, staff_user: Any) -> None:
        pages = staff_user.accessible_pages()

        assert "perm.admin.orders" in pages
        assert "perm.admin.finance" not in pages
        assert "perm.admin.users" not in pages
