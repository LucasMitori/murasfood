"""
System diagnostics.

Two things are being protected here. The first is that the page answers at all
when the thing it is diagnosing is broken — a diagnostics screen that fails
along with its dependency removes the one view that would have said so. The
second is that it never leaks: it is the most detail-rich endpoint in the
system, and it is reachable by anyone holding one permission code.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from apps.common.diagnostics import (
    DEGRADED,
    DOWN,
    OK,
    _safe_error,
    check_cache,
    check_configuration,
    check_database,
    run_diagnostics,
)

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/v1/admin/system/diagnostics/"


class TestProbesNeverRaise:
    """Every probe reports a failure rather than becoming one."""

    def test_a_dead_database_is_reported_not_raised(self) -> None:
        with mock.patch(
            "apps.common.diagnostics.connection.cursor", side_effect=OSError("connection refused")
        ):
            check = check_database()

        assert check.status == DOWN
        assert "OSError" in check.detail

    def test_a_dead_cache_is_reported_not_raised(self) -> None:
        with mock.patch(
            "apps.common.diagnostics.cache.set", side_effect=RuntimeError("redis is gone")
        ):
            check = check_cache()

        assert check.status == DOWN

    def test_a_cache_that_cannot_read_back_is_degraded(self) -> None:
        """Accepting writes it cannot serve is worse than being plainly down."""
        with mock.patch("apps.common.diagnostics.cache.get", return_value=None):
            check = check_cache()

        assert check.status == DEGRADED

    def test_the_whole_report_survives_a_broken_dependency(self) -> None:
        with mock.patch(
            "apps.common.diagnostics.cache.set", side_effect=RuntimeError("redis is gone")
        ):
            report = run_diagnostics(tenant_id=None)

        assert report["status"] in {DEGRADED, DOWN}
        assert len(report["checks"]) >= 8


class TestNothingSensitiveEscapes:
    def test_a_connection_string_is_never_echoed(self) -> None:
        """Driver exceptions cheerfully include the DSN they failed on, and a
        DSN carries a password."""
        error = OSError("could not connect to postgres://user:hunter2@db:5432/app")

        message = _safe_error(error)

        assert "hunter2" not in message
        assert "postgres://" not in message
        assert message == "OSError"

    @pytest.mark.parametrize(
        "text",
        [
            "invalid password for user",
            "bad SECRET value",
            "auth failed: token=abc123",
            "AWS key=AKIAIOSFODNN7EXAMPLE",
        ],
    )
    def test_anything_that_smells_of_a_credential_is_reduced_to_a_type(self, text: str) -> None:
        assert _safe_error(ValueError(text)) == "ValueError"

    def test_the_payload_carries_no_secret(self, tenant: Any) -> None:
        """A blunt sweep of the whole response. The point is that nobody has to
        remember to check a new field — every one of them is covered."""
        from django.conf import settings

        body = json.dumps(run_diagnostics(tenant_id=tenant.pk))

        assert settings.SECRET_KEY not in body
        for value in (settings.DATABASES["default"].get("PASSWORD"), settings.S3_SECRET_KEY):
            if value:
                assert value not in body

    def test_it_says_whether_a_key_is_set_not_what_it_is(self, settings: Any) -> None:
        """A boolean, never the value.

        Naming the *setting* in a warning is fine and useful — "SECRET_KEY is
        shorter than 50 characters" is exactly what an operator needs. What must
        never appear is what it is set to, and not even a masked prefix: a
        masked secret still discloses its length and shape.
        """
        settings.SECRET_KEY = "a-very-distinctive-development-secret-value"

        check = check_configuration()
        payload = json.dumps(check.meta)

        assert check.meta["secret_key_set"] is True
        assert settings.SECRET_KEY not in payload
        # Not even a fragment of it.
        assert settings.SECRET_KEY[:8] not in payload


class TestConfigurationWarnings:
    def test_debug_on_is_flagged(self, settings: Any) -> None:
        """It leaks tracebacks with local variables in them and breaks nothing
        visibly, which is exactly why it belongs on this page."""
        settings.DEBUG = True

        check = check_configuration()

        assert check.status == DEGRADED
        assert "DEBUG is on" in check.meta["warnings"]

    def test_a_clean_configuration_passes(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.SECRET_KEY = "x" * 60
        settings.ALLOWED_HOSTS = ["shop.example.com"]
        settings.SECURE_SSL_REDIRECT = True

        check = check_configuration()

        assert check.status == OK
        assert check.meta["warnings"] == []

    def test_a_wildcard_host_in_production_is_flagged(self, settings: Any) -> None:
        settings.DEBUG = False
        settings.SECRET_KEY = "x" * 60
        settings.ALLOWED_HOSTS = ["*"]

        check = check_configuration()

        assert any("ALLOWED_HOSTS" in warning for warning in check.meta["warnings"])


class TestAccess:
    def test_a_visitor_is_refused(self, api_client: Any) -> None:
        assert api_client.get(ENDPOINT).status_code in {401, 403}

    def test_a_customer_is_refused(self, customer_client: Any) -> None:
        assert customer_client.get(ENDPOINT).status_code == 403

    def test_staff_without_the_capability_are_refused(self, staff_client: Any) -> None:
        """The gate is the `system.diagnostics` capability, deliberately not a
        `perm.admin.*` page code: page codes are hierarchical, so a page code
        would hand queue depth and configuration warnings to everyone who can
        open the dashboard."""
        assert staff_client.get(ENDPOINT).status_code == 403

    def test_an_administrator_gets_the_report(self, admin_client_api: Any) -> None:
        response = admin_client_api.get(ENDPOINT)

        assert response.status_code == 200
        assert "checks" in response.json()

    def test_the_answer_is_never_cached(self, admin_client_api: Any) -> None:
        """A stale answer to "is it working right now" is a wrong one."""
        response = admin_client_api.get(ENDPOINT)

        assert response["Cache-Control"] == "no-store"


class TestTenantScope:
    def test_the_snapshot_counts_only_this_shop(
        self, admin_client_api: Any, other_tenant: Any, product: Any, product_factory: Any
    ) -> None:
        from apps.catalog.models import Product

        Product.objects.filter(pk=product.pk).update(tenant=other_tenant)

        body = admin_client_api.get(ENDPOINT).json()

        assert body["tenant"]["products"] == 0
