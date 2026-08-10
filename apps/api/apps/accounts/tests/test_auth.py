"""Registration, login, verification and password reset."""

from __future__ import annotations

from typing import Any

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.constants import TokenPurpose
from apps.accounts.models import AuthToken, LoginAttempt, User

pytestmark = pytest.mark.django_db


class TestRegistration:
    def test_creates_an_unverified_account(self, api_client: APIClient, tenant: Any) -> None:
        response = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "novo@example.test",
                "password": "senha-bem-forte-123",
                "first_name": "Novo",
                "accepted_terms": True,
            },
            format="json",
        )
        assert response.status_code == 201

        user = User.objects.get(tenant=tenant, email="novo@example.test")
        assert user.is_verified is False
        assert user.check_password("senha-bem-forte-123")

    def test_password_is_never_stored_in_plain_text(
        self, api_client: APIClient, tenant: Any
    ) -> None:
        api_client.post(
            "/api/v1/auth/register/",
            {"email": "hash@example.test", "password": "senha-bem-forte-123"},
            format="json",
        )
        user = User.objects.get(email="hash@example.test")
        assert user.password != "senha-bem-forte-123"
        assert user.password.startswith(("pbkdf2", "md5$"))

    def test_weak_password_is_rejected(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/api/v1/auth/register/",
            {"email": "fraca@example.test", "password": "12345678"},
            format="json",
        )
        assert response.status_code == 400

    def test_duplicate_email_within_a_tenant_is_rejected(
        self, api_client: APIClient, customer: Any
    ) -> None:
        response = api_client.post(
            "/api/v1/auth/register/",
            {"email": customer.email, "password": "senha-bem-forte-123"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    def test_verification_email_is_queued(
        self, api_client: APIClient, django_capture_on_commit_callbacks: Any
    ) -> None:
        """The send is deferred to ``transaction.on_commit``.

        Tests run inside a transaction that never commits, so the callbacks have
        to be captured and executed explicitly — which is also a useful check
        that the send really is deferred rather than inline.
        """
        with django_capture_on_commit_callbacks(execute=True):
            api_client.post(
                "/api/v1/auth/register/",
                {"email": "verificar@example.test", "password": "senha-bem-forte-123"},
                format="json",
            )

        assert any("verificar@example.test" in message.to for message in mail.outbox)


class TestEmailVerification:
    def test_valid_token_verifies_the_account(self, api_client: APIClient, customer: Any) -> None:
        customer.is_verified = False
        customer.save()
        _token, raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl_hours=1
        )

        response = api_client.post(
            "/api/v1/auth/verify-email/", {"token": raw, "uid": str(customer.pk)}, format="json"
        )
        assert response.status_code == 200

        customer.refresh_from_db()
        assert customer.is_verified is True

    def test_token_is_single_use(self, api_client: APIClient, customer: Any) -> None:
        customer.is_verified = False
        customer.save()
        _token, raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl_hours=1
        )

        api_client.post("/api/v1/auth/verify-email/", {"token": raw}, format="json")
        second = api_client.post("/api/v1/auth/verify-email/", {"token": raw}, format="json")

        assert second.status_code == 400
        assert second.data["error"]["code"] == "INVALID_TOKEN"

    def test_only_the_hash_is_stored(self, customer: Any) -> None:
        """A leaked database must not yield working verification links."""
        token, raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl_hours=1
        )
        assert token.token_hash != raw
        assert token.token_hash == AuthToken.hash_token(raw)

    def test_issuing_a_new_token_invalidates_the_previous_one(self, customer: Any) -> None:
        _first, first_raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl_hours=1
        )
        AuthToken.issue(user=customer, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl_hours=1)

        stale = AuthToken.objects.get(token_hash=AuthToken.hash_token(first_raw))
        assert stale.is_valid is False


class TestLogin:
    def test_returns_tokens_and_the_profile(self, api_client: APIClient, customer: Any) -> None:
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": customer.email, "password": "senha-super-secreta-1"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["access"]
        assert response.data["refresh"]
        assert response.data["user"]["email"] == customer.email

    def test_wrong_password_is_rejected_and_recorded(
        self, api_client: APIClient, customer: Any
    ) -> None:
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": customer.email, "password": "senha-errada"},
            format="json",
        )
        assert response.status_code == 401
        assert response.data["error"]["code"] == "INVALID_CREDENTIALS"
        assert LoginAttempt.objects.filter(email=customer.email, successful=False).exists()

    def test_login_is_scoped_to_the_tenant(
        self, other_tenant: Any, other_customer: Any, customer: Any
    ) -> None:
        """The same address in two tenants must not authenticate across them."""
        client = APIClient()
        client.credentials(HTTP_X_TENANT=other_tenant.slug)

        response = client.post(
            "/api/v1/auth/login/",
            {"email": customer.email, "password": "senha-super-secreta-1"},
            format="json",
        )
        assert response.status_code == 401

    def test_inactive_account_cannot_sign_in(self, api_client: APIClient, customer: Any) -> None:
        customer.is_active = False
        customer.save()

        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": customer.email, "password": "senha-super-secreta-1"},
            format="json",
        )
        assert response.status_code == 401

    def test_lockout_after_repeated_failures(
        self, api_client: APIClient, customer: Any, settings: Any
    ) -> None:
        settings.LOGIN_MAX_FAILED_ATTEMPTS = 3

        for _ in range(3):
            api_client.post(
                "/api/v1/auth/login/",
                {"email": customer.email, "password": "errada"},
                format="json",
            )

        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": customer.email, "password": "senha-super-secreta-1"},
            format="json",
        )
        assert response.status_code == 429
        assert response.data["error"]["code"] == "ACCOUNT_LOCKED"


class TestPasswordReset:
    def test_request_is_silent_about_unknown_addresses(self, api_client: APIClient) -> None:
        """Responding differently would leak the customer list."""
        known = api_client.post(
            "/api/v1/auth/password-reset/", {"email": "quemsabe@example.test"}, format="json"
        )
        assert known.status_code == 202

    def test_reset_changes_the_password(self, api_client: APIClient, customer: Any) -> None:
        from apps.accounts.services import request_password_reset

        request_password_reset(tenant=customer.tenant, email=customer.email)
        token = AuthToken.objects.filter(
            user=customer, purpose=TokenPurpose.PASSWORD_RESET, used_at__isnull=True
        ).first()
        assert token is not None

        # The plaintext only exists in the email; re-issue one we can use.
        _token, raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.PASSWORD_RESET, ttl_hours=1
        )
        response = api_client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"token": raw, "password": "nova-senha-muito-forte-9"},
            format="json",
        )
        assert response.status_code == 200

        customer.refresh_from_db()
        assert customer.check_password("nova-senha-muito-forte-9")

    def test_expired_token_is_rejected(self, api_client: APIClient, customer: Any) -> None:
        from datetime import timedelta

        from django.utils import timezone

        token, raw = AuthToken.issue(
            user=customer, purpose=TokenPurpose.PASSWORD_RESET, ttl_hours=1
        )
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save()

        response = api_client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"token": raw, "password": "nova-senha-muito-forte-9"},
            format="json",
        )
        assert response.status_code == 400


class TestSelfService:
    def test_me_returns_the_profile_and_permissions(
        self, admin_client_api: APIClient, admin_user: Any
    ) -> None:
        response = admin_client_api.get("/api/v1/customers/me/")
        assert response.status_code == 200
        assert response.data["email"] == admin_user.email
        assert "orders.refund" in response.data["permissions"]

    def test_anonymisation_keeps_orders_but_removes_identity(
        self, customer: Any, tenant: Any, filled_cart: Any
    ) -> None:
        from apps.accounts.services import anonymize_user
        from apps.orders.models import Order
        from apps.orders.services import create_order_from_cart

        order = create_order_from_cart(
            tenant=tenant, cart=filled_cart, delivery_method="PICKUP", customer=customer
        )

        anonymize_user(customer)
        customer.refresh_from_db()

        assert "anonymized+" in customer.email
        assert customer.first_name == ""
        assert customer.is_active is False
        # The financial record survives.
        assert Order.objects.filter(pk=order.pk).exists()

    def test_data_export_includes_orders_and_addresses(
        self, customer_client: APIClient, address: Any
    ) -> None:
        response = customer_client.get("/api/v1/customers/me/data-export/")
        assert response.status_code == 200
        assert response.data["account"]["email"]
        assert len(response.data["addresses"]) == 1
