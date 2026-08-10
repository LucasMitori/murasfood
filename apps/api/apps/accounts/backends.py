"""
Authentication backend.

Email is unique *per tenant*, not globally: the same person may hold a separate
account at two merchants running on the same deployment. Django's stock
``ModelBackend`` calls ``get_by_natural_key(email)`` and would raise
``MultipleObjectsReturned`` the moment that happens, so authentication has to be
tenant-aware.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password, make_password

from .models import User

if TYPE_CHECKING:  # pragma: no cover
    from django.http import HttpRequest

# Hashing a throwaway password on the failure path keeps the response time for
# "unknown account" close to "wrong password", so the endpoint is not a cheap
# account-enumeration oracle.
_DUMMY_HASH = make_password("murasfood-timing-equaliser")


class TenantModelBackend(ModelBackend):
    """Authenticate an email/password pair within a tenant."""

    def authenticate(  # type: ignore[override]
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or password is None:
            return None

        tenant = kwargs.get("tenant") or getattr(request, "tenant", None)
        candidates = self._candidates(email, tenant)

        if len(candidates) != 1:
            # Either no such account, or an ambiguous match we refuse to guess at.
            check_password(password, _DUMMY_HASH)
            return None

        user = candidates[0]
        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        return user

    @staticmethod
    def _candidates(email: str, tenant: Any | None) -> list[User]:
        """Find the account this email refers to, most specific match first."""
        base = User.objects.filter(email__iexact=email)

        if tenant is not None:
            scoped = list(base.filter(tenant=tenant)[:2])
            if scoped:
                return scoped

        # Platform administrators have no tenant.
        platform = list(base.filter(tenant__isnull=True)[:2])
        if platform:
            return platform

        # Single-merchant deployments: an unambiguous match is safe to accept.
        return list(base[:2])

    def get_user(self, user_id: Any) -> User | None:
        return User.objects.filter(pk=user_id, is_active=True).first()
