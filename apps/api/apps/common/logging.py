"""
Structured logging.

Production emits one JSON object per line so a log shipper can index fields
directly. Development keeps a readable console format.

Secrets never reach the logs: :data:`REDACTED_KEYS` is applied to every extra
field, and request/response bodies are not logged at all (rule #11 of the
critical invariants).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .context import get_actor_id, get_request_id, get_tenant_id

REDACTED_KEYS = frozenset(
    {
        "password",
        "password1",
        "password2",
        "new_password",
        "current_password",
        "token",
        "access",
        "refresh",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "webhook_secret",
        "signature",
        "card_number",
        "cvv",
        "smtp_password",
    }
)

_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        "request_id",
    }
)


def redact(value: Any, key: str = "") -> Any:
    """Recursively replace sensitive values with ``"***"``."""
    if key.lower() in REDACTED_KEYS:
        return "***"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class RequestIDFilter(logging.Filter):
    """Attaches the ambient request id to every record.

    Registered as a filter rather than injected by callers so third-party log
    lines (Django, Celery) are correlated too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """Formats records as single-line JSON with the ambient request context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }

        tenant_id = get_tenant_id()
        if tenant_id:
            payload["tenant_id"] = tenant_id
        actor_id = get_actor_id()
        if actor_id:
            payload["actor_id"] = actor_id

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact(value, key)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)
