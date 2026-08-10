"""
Payment provider implementations.

The application depends on :class:`~apps.payments.providers.base.PaymentProvider`
and never on a specific PSP (ADR-005). Switching from one Brazilian acquirer to
another is a new module here plus an environment variable — no change to
checkout, orders or reporting.
"""

from __future__ import annotations

from django.conf import settings

from .base import PaymentProvider, PaymentResult, RefundResult, WebhookEvent
from .sandbox import SandboxPixProvider

#: ``PAYMENT_PROVIDER`` value -> implementation.
PROVIDER_REGISTRY: dict[str, type[PaymentProvider]] = {
    "sandbox": SandboxPixProvider,
}

_instances: dict[str, PaymentProvider] = {}


def get_provider(name: str | None = None) -> PaymentProvider:
    """Return the configured provider.

    Raises:
        ValueError: The configured name has no implementation — failing loudly
            at boot beats silently not charging anyone.
    """
    key = (name or settings.PAYMENT_PROVIDER or "sandbox").lower()
    if key not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown payment provider {key!r}. Registered: {sorted(PROVIDER_REGISTRY)}"
        )
    if key not in _instances:
        _instances[key] = PROVIDER_REGISTRY[key]()
    return _instances[key]


def reset_provider_cache() -> None:
    """Drop memoised providers. Used by tests that swap configuration."""
    _instances.clear()


__all__ = [
    "PROVIDER_REGISTRY",
    "PaymentProvider",
    "PaymentResult",
    "RefundResult",
    "SandboxPixProvider",
    "WebhookEvent",
    "get_provider",
    "reset_provider_cache",
]
