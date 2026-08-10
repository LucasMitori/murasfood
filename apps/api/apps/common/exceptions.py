"""
Error handling.

Every failure leaving the API uses one predictable envelope::

    {
      "error": {
        "code": "PRODUCT_OUT_OF_STOCK",
        "message": "Product is unavailable.",
        "details": {},
        "request_id": "1f2e..."
      }
    }

Clients switch on ``code``; ``message`` is for humans and is already localised
by Django's translation machinery. Stack traces never reach a response.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .context import get_request_id

logger = logging.getLogger("murasfood.errors")


class DomainError(APIException):
    """Base class for expected, business-rule failures.

    Subclasses declare a stable ``default_code`` that clients may branch on.
    Unlike a bare ``APIException`` these are *not* logged as server errors —
    "the cart is empty" is a normal outcome, not an incident.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("The request could not be completed.")
    default_code = "DOMAIN_ERROR"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(detail or self.default_detail, code or self.default_code)
        self.details = details or {}
        # Shadow the class attribute so a code supplied at the raise site is the
        # one clients see. Reading `type(exc).default_code` would silently
        # discard it and report the generic parent code instead.
        if code:
            self.default_code = code
        if status_code is not None:
            self.status_code = status_code


class ConflictError(DomainError):
    """The request collides with the current state of the resource."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = _("The resource is in a conflicting state.")
    default_code = "CONFLICT"


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("Resource not found.")
    default_code = "NOT_FOUND"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("You do not have permission to perform this action.")
    default_code = "FORBIDDEN"


class TenantResolutionError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("No store could be resolved for this request.")
    default_code = "TENANT_NOT_RESOLVED"


class CrossTenantAccessError(ForbiddenError):
    """Raised when a request touches data belonging to another tenant.

    This is a security event: it is always logged with the actor and the target.
    """

    default_detail = _("Resource not found.")  # do not confirm existence
    default_code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class InsufficientStockError(ConflictError):
    default_detail = _("There is not enough stock for one or more items.")
    default_code = "INSUFFICIENT_STOCK"


class InvalidStateTransitionError(ConflictError):
    default_detail = _("This status change is not allowed.")
    default_code = "INVALID_STATE_TRANSITION"


class PaymentError(DomainError):
    default_detail = _("The payment could not be processed.")
    default_code = "PAYMENT_ERROR"


class IdempotencyConflictError(ConflictError):
    default_detail = _("A different request was already made with this idempotency key.")
    default_code = "IDEMPOTENCY_KEY_REUSED"


def _build_envelope(
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, dict[str, Any]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


def _extract_code(exc: Exception, default: str) -> str:
    code = getattr(exc, "default_code", None) or getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code.upper()
    return default


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler producing the MurasFood error envelope.

    Anything unhandled is re-raised so Django's own 500 machinery (and the error
    tracker) sees it; DEBUG=False then returns an opaque response.
    """
    # Normalise Django-native exceptions to their DRF equivalents first.
    if isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(
            detail=exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
    elif isinstance(exc, PermissionDenied):
        exc = ForbiddenError(str(exc) or None)
    elif isinstance(exc, Http404):
        exc = NotFoundError()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, DRFValidationError):
        payload = _build_envelope(
            "VALIDATION_ERROR",
            str(_("Some fields are invalid.")),
            details=response.data if isinstance(response.data, dict | list) else {},
        )
    elif isinstance(exc, DomainError):
        payload = _build_envelope(exc.default_code, str(exc.detail), exc.details)
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        payload = _build_envelope(
            _extract_code(exc, "ERROR"),
            str(detail or exc),
        )

    if isinstance(exc, CrossTenantAccessError):
        logger.warning(
            "cross_tenant_access_blocked",
            extra={"event": "security.cross_tenant_access", "details": exc.details},
        )

    response.data = payload
    return response
