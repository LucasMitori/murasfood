"""Audit writing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.common.context import get_request_id
from apps.common.logging import redact

from .models import AuditLog

if TYPE_CHECKING:  # pragma: no cover
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.audit")

#: Values longer than this are truncated: an audit row records *that* something
#: changed, not a full document dump.
MAX_VALUE_LENGTH = 2000


def _serialisable(values: Any) -> dict[str, Any]:
    """Redact secrets and trim oversized values before persisting."""
    if not isinstance(values, dict):
        return {}

    cleaned: dict[str, Any] = {}
    for key, value in redact(values).items():
        text = value if isinstance(value, int | float | bool | type(None)) else str(value)
        if isinstance(text, str) and len(text) > MAX_VALUE_LENGTH:
            text = text[:MAX_VALUE_LENGTH] + "…"
        cleaned[key] = text
    return cleaned


def record_audit(
    *,
    action: str,
    tenant: Tenant | None = None,
    actor: Any | None = None,
    resource: Any | None = None,
    old_values: Any = None,
    new_values: Any = None,
    request: Any = None,
) -> AuditLog | None:
    """Write one audit row.

    Never raises: an audit failure must not break the business operation that
    triggered it. Failures are logged loudly instead so they surface in
    monitoring.

    Args:
        action: Dotted action name, e.g. ``"pricing.price_changed"``.
        tenant: Owning tenant; ``None`` for platform-level actions.
        actor: The acting user, or ``None`` for system/webhook actions.
        resource: The affected object; its class name and pk are recorded.
        old_values / new_values: Before/after snapshots, redacted on the way in.
        request: Used to capture IP and user agent.
    """
    try:
        actor_obj = (
            actor
            if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True)
            else None
        )

        ip = None
        user_agent = ""
        if request is not None:
            meta = getattr(request, "META", {})
            forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
            ip = forwarded.split(",")[0].strip() if forwarded else meta.get("REMOTE_ADDR")
            user_agent = meta.get("HTTP_USER_AGENT", "")[:255]

        return AuditLog.objects.create(
            tenant=tenant,
            actor=actor_obj,
            actor_label=str(actor_obj) if actor_obj is not None else "system",
            action=action,
            resource_type=resource.__class__.__name__ if resource is not None else "",
            resource_id=str(getattr(resource, "pk", "") or "")[:64],
            old_values=_serialisable(old_values),
            new_values=_serialisable(new_values),
            ip_address=ip,
            user_agent=user_agent,
            request_id=get_request_id(),
        )
    except Exception:
        logger.exception(
            "audit_write_failed", extra={"event": "audit.write_failed", "action": action}
        )
        return None
