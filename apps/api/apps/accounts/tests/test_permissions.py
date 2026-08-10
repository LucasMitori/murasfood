"""
Role and permission enforcement.

Authorization is by permission code, never by role name (spec §7). These tests
check both the code layer and the HTTP layer.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.constants import ALL_PERMISSION_CODES, SystemRole
from apps.accounts.models import Permission, Role

pytestmark = pytest.mark.django_db


class TestProvisioning:
    def test_every_catalogue_code_exists_after_bootstrap(self, tenant: Any) -> None:
        stored = set(Permission.objects.values_list("code", flat=True))
        assert set(ALL_PERMISSION_CODES).issubset(stored)

    def test_system_roles_are_created_per_tenant(self, tenant: Any) -> None:
        slugs = set(Role.objects.filter(tenant=tenant).values_list("slug", flat=True))
        assert slugs == {SystemRole.STAFF, SystemRole.MANAGER, SystemRole.ADMINISTRATOR}

    def test_bootstrap_is_idempotent(self, tenant: Any) -> None:
        from apps.accounts.services import ensure_system_roles

        before = Role.objects.filter(tenant=tenant).count()
        ensure_system_roles(tenant)
        assert Role.objects.filter(tenant=tenant).count() == before


class TestPermissionChecks:
    def test_administrator_holds_everything(self, admin_user: Any) -> None:
        assert admin_user.permission_codes() == set(ALL_PERMISSION_CODES)

    def test_staff_holds_a_subset(self, staff_user: Any) -> None:
        assert staff_user.has_permission_code("orders.view") is True
        assert staff_user.has_permission_code("orders.refund") is False
        assert staff_user.has_permission_code("finance.manage") is False

    def test_customer_holds_only_their_own_account_area(self, customer: Any) -> None:
        """A shopper needs no grant to reach their own profile.

        They hold the `perm.account` page namespace and nothing else — no
        capability code, and no part of the dashboard.
        """
        assert customer.permission_codes() == {"perm.account"}
        assert customer.has_permission_code("perm.account.profile") is True
        assert customer.has_permission_code("perm.admin") is False
        assert customer.has_permission_code("orders.view") is False

    def test_unknown_code_denies(self, admin_user: Any) -> None:
        """A typo in a view must fail closed, not open."""
        assert admin_user.has_permission_code("catalog.destroy_everything") is False

    def test_deactivated_user_loses_access(self, admin_user: Any) -> None:
        admin_user.is_active = False
        assert admin_user.has_permission_code("orders.view") is False

    def test_granting_a_role_updates_the_cache(self, tenant: Any, customer: Any) -> None:
        from apps.accounts.services import assign_role

        assert customer.has_permission_code("orders.view") is False

        assign_role(customer, Role.objects.get(tenant=tenant, slug=SystemRole.STAFF))
        assert customer.has_permission_code("orders.view") is True


class TestEndpointAuthorization:
    def test_customer_cannot_reach_the_dashboard(self, customer_client: APIClient) -> None:
        assert customer_client.get("/api/v1/admin/dashboard/").status_code == 403

    def test_staff_cannot_read_finance(self, staff_client: APIClient) -> None:
        assert staff_client.get("/api/v1/admin/finance/summary/").status_code == 403

    def test_admin_can_read_finance(self, admin_client_api: APIClient) -> None:
        assert admin_client_api.get("/api/v1/admin/finance/summary/").status_code == 200

    def test_staff_can_view_but_not_change_prices(
        self, staff_client: APIClient, product: Any
    ) -> None:
        assert staff_client.get("/api/v1/admin/prices/").status_code == 200

        response = staff_client.post(
            "/api/v1/admin/prices/set/",
            {"product": str(product.pk), "base_price": "1.00"},
            format="json",
        )
        assert response.status_code == 403

    def test_anonymous_cannot_read_the_audit_log(self, api_client: APIClient) -> None:
        assert api_client.get("/api/v1/admin/audit-logs/").status_code in (401, 403)

    def test_staff_cannot_deactivate_users(self, staff_client: APIClient, admin_user: Any) -> None:
        response = staff_client.delete(f"/api/v1/admin/users/{admin_user.pk}/")
        assert response.status_code == 403

    def test_administrator_cannot_deactivate_themselves(
        self, admin_client_api: APIClient, admin_user: Any
    ) -> None:
        response = admin_client_api.delete(f"/api/v1/admin/users/{admin_user.pk}/")
        assert response.status_code == 400
        assert response.data["error"]["code"] == "SELF_DEACTIVATION"

    def test_system_roles_cannot_be_deleted(self, admin_client_api: APIClient, tenant: Any) -> None:
        role = Role.objects.get(tenant=tenant, slug=SystemRole.STAFF)
        response = admin_client_api.delete(f"/api/v1/admin/roles/{role.pk}/")

        assert response.status_code == 400
        assert response.data["error"]["code"] == "SYSTEM_ROLE_PROTECTED"
