"""The CORS contract the storefront depends on.

These assert configuration, which is unusual for a test suite — but a browser
enforces CORS silently. Drop a header from either list and nothing raises, no
log line appears, and the only symptom is a feature that stops working in the
browser while every curl and every API test still passes.

Both entries below have already failed in exactly that way: the anonymous cart
was unusable because `X-Cart-Token` was sent by the API but never exposed to
JavaScript, and then blocked by the preflight when the client tried to send it
back.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.test import Client


def test_cart_token_may_be_sent_by_the_browser() -> None:
    """Omitting it does not hide a header — the preflight fails the request."""
    assert "x-cart-token" in [header.lower() for header in settings.CORS_ALLOW_HEADERS]


def test_cart_token_may_be_read_by_javascript() -> None:
    """A cross-origin response exposes only safelisted headers by default."""
    assert "X-Cart-Token" in settings.CORS_EXPOSE_HEADERS


def test_tenant_and_idempotency_headers_are_allowed() -> None:
    allowed = [header.lower() for header in settings.CORS_ALLOW_HEADERS]
    for header in ("x-tenant", "idempotency-key", "authorization"):
        assert header in allowed


def test_preflight_accepts_the_storefront_headers(client: Client) -> None:
    """The end-to-end check: what a browser actually asks before a cart call."""
    response = client.options(
        "/api/v1/cart/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-cart-token,x-tenant",
    )

    assert response.status_code == 200
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-cart-token" in allowed
    assert "x-tenant" in allowed


@pytest.mark.django_db
def test_preflight_advertises_the_readable_headers(client: Client, tenant: Any) -> None:
    response = client.get(
        "/api/v1/cart/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_X_TENANT=tenant.slug,
    )

    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Cart-Token" in exposed
