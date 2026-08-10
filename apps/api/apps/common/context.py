"""
Per-request ambient context.

Middleware stores the request id and the resolved tenant here so that logging,
audit records and Celery tasks can pick them up without threading arguments
through every function signature. Context variables are coroutine-safe and are
reset at the end of each request.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_actor_id: ContextVar[str | None] = ContextVar("actor_id", default=None)


def new_request_id() -> str:
    """Return a fresh request identifier."""
    return uuid.uuid4().hex


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


def set_tenant_id(value: Any | None) -> None:
    _tenant_id.set(str(value) if value else None)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def set_actor_id(value: Any | None) -> None:
    _actor_id.set(str(value) if value else None)


def get_actor_id() -> str | None:
    return _actor_id.get()


def reset() -> None:
    """Clear every context variable. Called when a request finishes."""
    _request_id.set("-")
    _tenant_id.set(None)
    _actor_id.set(None)


@contextmanager
def request_context(
    *,
    request_id: str | None = None,
    tenant_id: Any | None = None,
    actor_id: Any | None = None,
) -> Iterator[None]:
    """Temporarily bind a context, restoring the previous values on exit.

    Useful in Celery tasks and management commands, which have no HTTP request
    but still need their log lines correlated with the work that scheduled them.
    """
    tokens = (
        _request_id.set(request_id or new_request_id()),
        _tenant_id.set(str(tenant_id) if tenant_id else None),
        _actor_id.set(str(actor_id) if actor_id else None),
    )
    try:
        yield
    finally:
        _request_id.reset(tokens[0])
        _tenant_id.reset(tokens[1])
        _actor_id.reset(tokens[2])
