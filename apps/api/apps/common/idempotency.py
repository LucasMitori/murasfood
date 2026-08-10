"""
Idempotency for money-moving operations.

A client sends ``Idempotency-Key: <uuid>`` with a create-order, create-payment
or refund request. The first request executes and its response is stored; any
replay with the same key and the same payload returns the stored response
instead of charging the customer twice (spec §49, invariant #5).

Replaying a key with a *different* payload is a client bug and is rejected with
``IDEMPOTENCY_KEY_REUSED`` rather than silently returning the wrong result.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from .exceptions import IdempotencyConflictError
from .models import IdempotencyRecord

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from rest_framework.request import Request

IDEMPOTENCY_HEADER = "HTTP_IDEMPOTENCY_KEY"


def hash_payload(payload: Any) -> str:
    """Stable SHA-256 of a JSON-serialisable payload."""
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _jsonify(body: Any) -> Any:
    """Convert a serializer's output into something ``JSONField`` accepts.

    DRF hands back ``UUID``, ``Decimal`` and ``datetime`` objects, none of which
    the stock JSON encoder can write. Storing the response is the whole point of
    an idempotency record, so this must not be left to chance — an unencodable
    body would turn a successful checkout into a 500 on the *first* call.
    """
    from django.core.serializers.json import DjangoJSONEncoder

    if not isinstance(body, dict | list):
        return {}
    return json.loads(json.dumps(body, cls=DjangoJSONEncoder))


def extract_key(request: Request) -> str | None:
    """Read the ``Idempotency-Key`` header, if present."""
    raw = request.META.get(IDEMPOTENCY_HEADER, "").strip()
    return raw[:255] or None


def run_idempotent(
    *,
    key: str | None,
    scope: str,
    payload: Any,
    tenant_id: Any | None,
    user_id: Any | None,
    ttl_seconds: int,
    operation: Callable[[], tuple[int, Any]],
) -> tuple[int, Any, bool]:
    """Execute ``operation`` at most once per ``key``.

    Args:
        key: Client-supplied idempotency key. When ``None`` the operation runs
            normally without any replay protection.
        scope: Operation name, e.g. ``"checkout"``. Keeps keys from colliding
            across unrelated endpoints.
        payload: Request payload used to detect key reuse with different data.
        tenant_id: Tenant the operation belongs to; keys are scoped per tenant.
        user_id: Actor, stored for troubleshooting only.
        ttl_seconds: How long a stored response stays replayable.
        operation: Callable returning ``(status_code, body)``.

    Returns:
        ``(status_code, body, replayed)`` where ``replayed`` tells the caller the
        result came from a previous execution.

    Raises:
        IdempotencyConflictError: The key was already used with a different
            payload.
    """
    if not key:
        status_code, body = operation()
        return status_code, body, False

    request_hash = hash_payload(payload)
    existing = IdempotencyRecord.objects.filter(
        scope=scope, key=key, tenant_id_value=tenant_id
    ).first()

    if existing is not None:
        if existing.expires_at > timezone.now():
            if existing.request_hash != request_hash:
                raise IdempotencyConflictError(details={"scope": scope, "key": key})
            return existing.response_status, existing.response_body, True
        # Expired: the key may be recycled.
        existing.delete()

    status_code, body = operation()

    try:
        with transaction.atomic():
            IdempotencyRecord.objects.create(
                scope=scope,
                key=key,
                tenant_id_value=tenant_id,
                user_id_value=user_id,
                request_hash=request_hash,
                response_status=status_code,
                response_body=_jsonify(body),
                expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
            )
    except IntegrityError:
        # A concurrent request won the race; its stored response is canonical.
        winner = IdempotencyRecord.objects.filter(
            scope=scope, key=key, tenant_id_value=tenant_id
        ).first()
        if winner is not None:
            return winner.response_status, winner.response_body, True

    return status_code, body, False
