"""
Request middleware.

``RequestIDMiddleware``
    Assigns (or accepts) a correlation id and echoes it back on the response.

``TenantMiddleware``
    Performs a *preliminary* tenant resolution from the ``X-Tenant`` header or
    the request subdomain. It cannot look at the authenticated user because JWT
    authentication happens later, inside the DRF view — the authoritative
    resolution therefore happens again in
    :class:`apps.common.views.TenantScopedMixin`, which always wins.

``AccessLogMiddleware``
    One structured log line per request. Bodies are never logged.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from django.utils.deprecation import MiddlewareMixin

from . import context

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("murasfood.access")

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"
TENANT_HEADER = "HTTP_X_TENANT"

# Paths that must stay cheap and dependency-free.
SILENT_PATHS = ("/health/live/", "/health/ready/", "/static/")


class RequestIDMiddleware(MiddlewareMixin):
    """Correlates every log line, audit row and error response with one request."""

    def process_request(self, request: HttpRequest) -> None:
        incoming = request.META.get(REQUEST_ID_HEADER, "").strip()
        # Trust the caller's id only when it looks sane: it ends up in logs.
        request_id = (
            incoming if incoming.isalnum() and len(incoming) <= 64 else context.new_request_id()
        )
        request.request_id = request_id  # type: ignore[attr-defined]
        context.set_request_id(request_id)

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        response[REQUEST_ID_RESPONSE_HEADER] = getattr(
            request, "request_id", context.get_request_id()
        )
        context.reset()
        return response


class TenantMiddleware(MiddlewareMixin):
    """Attaches a best-effort ``request.tenant`` before the view runs."""

    def process_request(self, request: HttpRequest) -> None:
        from apps.tenants.resolver import resolve_tenant_from_request

        tenant = resolve_tenant_from_request(request)
        request.tenant = tenant  # type: ignore[attr-defined]
        request.tenant_id = tenant.pk if tenant else None  # type: ignore[attr-defined]
        context.set_tenant_id(tenant.pk if tenant else None)


class AccessLogMiddleware:
    """Emits ``method path -> status`` with latency and the resolved actor."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.monotonic()
        response = self.get_response(request)

        if request.path.startswith(SILENT_PATHS):
            return response

        user = getattr(request, "user", None)
        actor_id = str(user.pk) if user is not None and user.is_authenticated else None
        context.set_actor_id(actor_id)

        logger.info(
            "%s %s -> %s",
            request.method,
            request.path,
            response.status_code,
            extra={
                "event": "http.request",
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "actor_id": actor_id,
                "tenant_id": str(getattr(request, "tenant_id", "") or "") or None,
            },
        )
        return response
