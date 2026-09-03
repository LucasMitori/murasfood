"""
Notification services.

Sending is always asynchronous (spec §87): the HTTP request that creates an
order must not wait on an SMTP handshake. Every send is logged, retried with
backoff, and de-duplicated by an idempotency key so a customer never receives
"your order is ready" twice.
"""

from __future__ import annotations

import html
import logging
import re
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import EmailLog, EmailStatus, EmailTemplate, Notification, NotificationStatus
from .templates_seed import DEFAULT_TEMPLATES, ORDER_STATUS_TEMPLATES

if TYPE_CHECKING:  # pragma: no cover
    from apps.accounts.models import User
    from apps.orders.models import Order
    from apps.tenants.models import Tenant

logger = logging.getLogger("murasfood.notifications")

#: Matches ``{{ variable_name }}`` with optional surrounding whitespace.
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_template(source: str, context: dict[str, Any], *, escape: bool = True) -> str:
    """Substitute ``{{ placeholders }}`` with values from ``context``.

    Deliberately *not* a real template engine. Merchant-editable templates must
    never be able to execute code or reach into objects, so this does literal
    substitution and nothing else. Unknown placeholders render empty rather than
    leaking ``{{ secret_key }}`` into an email.
    """

    def replace(match: re.Match[str]) -> str:
        value = context.get(match.group(1), "")
        text = "" if value is None else str(value)
        return html.escape(text) if escape else text

    return _PLACEHOLDER.sub(replace, source or "")


def seed_default_templates(tenant: Tenant, *, locale: str | None = None) -> int:
    """Install the default templates for a tenant. Idempotent."""
    target_locale = locale or tenant.locale or "pt-BR"
    created = 0
    for spec in DEFAULT_TEMPLATES:
        _template, was_created = EmailTemplate.objects.get_or_create(
            tenant=tenant,
            key=spec["key"],
            locale=target_locale,
            defaults={
                "subject": spec["subject"],
                "html_body": spec["html"],
                "text_body": spec["text"],
                "available_variables": spec["variables"],
            },
        )
        created += int(was_created)
    return created


def _find_template(tenant: Tenant, key: str, locale: str | None) -> EmailTemplate | None:
    """Best matching template: exact locale, then language, then any."""
    candidates = EmailTemplate.objects.filter(tenant=tenant, key=key, is_active=True)
    wanted = locale or tenant.locale or "pt-BR"

    exact = candidates.filter(locale__iexact=wanted).first()
    if exact is not None:
        return exact

    language = wanted.split("-")[0]
    language_match = candidates.filter(locale__istartswith=language).first()
    return language_match or candidates.first()


def _base_context(tenant: Tenant) -> dict[str, Any]:
    return {
        "store_name": tenant.trade_name,
        "support_email": tenant.support_email,
        "locale": tenant.locale,
        "app_url": settings.PUBLIC_APP_URL,
        # The layout has a hidden preheader slot — the grey line a mail client
        # shows next to the subject. Defaulted here so an unset one renders as
        # nothing rather than as the literal placeholder.
        "preheader": "",
    }


def queue_transactional_email(
    *,
    tenant: Tenant | None,
    template_key: str,
    recipient: str,
    context: dict[str, Any] | None = None,
    user: User | None = None,
    related_type: str = "",
    related_id: str = "",
    idempotency_key: str = "",
    locale: str | None = None,
) -> EmailLog | None:
    """Record an email and hand it to the worker.

    Returns ``None`` when the message was already queued under the same
    idempotency key, or when no tenant/recipient is available.
    """
    if tenant is None or not recipient:
        return None

    template = _find_template(tenant, template_key, locale)
    if template is None:
        # Missing templates are a configuration bug, not a reason to crash the
        # order that triggered them.
        logger.warning(
            "email_template_missing",
            extra={"event": "notifications.template_missing", "template_key": template_key},
        )
        return None

    merged = {**_base_context(tenant), **(context or {})}
    subject = render_template(template.subject, merged, escape=False)

    try:
        with transaction.atomic():
            log = EmailLog.objects.create(
                tenant=tenant,
                template_key=template_key,
                recipient=recipient,
                subject=subject[:255],
                related_type=related_type[:32],
                related_id=str(related_id)[:64],
                idempotency_key=idempotency_key[:128],
                user=user,
            )
    except IntegrityError:
        logger.info(
            "email_already_queued",
            extra={"event": "notifications.duplicate", "template_key": template_key},
        )
        return None

    from .tasks import send_email

    # Queue only once the surrounding transaction commits, so the worker never
    # picks up a log row that was rolled back.
    transaction.on_commit(lambda: send_email.delay(str(log.pk), merged))
    return log


def deliver_email(log: EmailLog, context: dict[str, Any]) -> bool:
    """Render and send one email. Called from the Celery task.

    Returns ``True`` on success. Failures are recorded on the log and re-raised
    so Celery's retry policy applies.
    """
    from django.core.mail import EmailMultiAlternatives

    tenant = log.tenant
    template = _find_template(tenant, log.template_key, tenant.locale)
    if template is None:
        log.status = EmailStatus.FAILED
        log.last_error = "Template not found"
        log.save(update_fields=["status", "last_error", "updated_at"])
        return False

    merged = {**_base_context(tenant), **context}
    subject = render_template(template.subject, merged, escape=False)
    # Falls back to the subject, which is a better preview line than a blank.
    merged.setdefault("preheader", subject)
    if not merged.get("preheader"):
        merged["preheader"] = subject
    text_body = render_template(template.text_body or "", merged, escape=False)
    html_body = render_template(template.html_body, merged)

    settings_row = getattr(tenant, "settings", None)
    sender_name = (settings_row.email_sender_name if settings_row else "") or tenant.trade_name
    address = (settings_row.smtp_from_email if settings_row else "") or settings.DEFAULT_FROM_EMAIL
    from_email = f"{sender_name} <{address}>"

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body or re.sub(r"<[^>]+>", " ", html_body),
        from_email=from_email,
        to=[log.recipient],
        reply_to=[settings_row.email_reply_to]
        if settings_row and settings_row.email_reply_to
        else None,
        connection=connection_for(tenant),
    )
    message.attach_alternative(html_body, "text/html")

    from django.utils import timezone

    log.attempts += 1
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        log.status = (
            EmailStatus.RETRYING
            if log.attempts < settings.EMAIL_MAX_ATTEMPTS
            else EmailStatus.FAILED
        )
        log.last_error = str(exc)[:500]
        log.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        raise

    log.status = EmailStatus.SENT
    log.sent_at = timezone.now()
    log.last_error = ""
    log.save(update_fields=["status", "attempts", "sent_at", "last_error", "updated_at"])
    return True


# =============================================================================
# Domain notifications
# =============================================================================
def notify_order_status(order: Order, *, previous_status: str = "") -> EmailLog | None:
    """Email the customer about an order transition, if that status warrants one.

    The idempotency key is ``order:<id>:<status>``, so re-entering a status —
    a webhook replay, a manual re-send — cannot email the customer twice.
    """
    template_key = ORDER_STATUS_TEMPLATES.get(order.status)
    if template_key is None:
        return None

    recipient = order.customer_email or (order.customer.email if order.customer else "")
    if not recipient:
        return None

    log = queue_transactional_email(
        tenant=order.tenant,
        template_key=template_key,
        recipient=recipient,
        context={
            "first_name": (
                order.customer.get_short_name() if order.customer else order.customer_name
            )
            or "cliente",
            "order_number": order.number,
            "order_total": f"{order.currency} {order.total}",
            "order_url": f"{settings.PUBLIC_APP_URL}/account/orders/{order.number}",
            "reason": order.cancellation_reason,
        },
        user=order.customer,
        related_type="order",
        related_id=str(order.pk),
        idempotency_key=f"order:{order.pk}:{order.status}",
    )

    if order.customer_id:
        create_notification(
            user=order.customer,
            tenant=order.tenant,
            notification_type=f"order.{order.status.lower()}",
            title=f"Pedido {order.number}",
            body=str(order.get_status_display()),
            payload={"order_number": order.number, "status": order.status},
        )
    return log


def create_notification(
    *,
    user: User,
    tenant: Tenant,
    notification_type: str,
    title: str,
    body: str = "",
    payload: dict[str, Any] | None = None,
    channel: str = "IN_APP",
) -> Notification:
    """Record an in-app notification."""
    return Notification.objects.create(
        tenant=tenant,
        user=user,
        channel=channel,
        notification_type=notification_type,
        title=title[:160],
        body=body[:500],
        payload=payload or {},
        status=NotificationStatus.SENT,
    )


def notify_staff_new_order(order: Order) -> EmailLog | None:
    """Tell the merchant an order came in, when they have opted into that."""
    settings_row = getattr(order.tenant, "settings", None)
    if not (settings_row and settings_row.notify_on_new_order):
        return None

    return queue_transactional_email(
        tenant=order.tenant,
        template_key="order.created",
        recipient=order.tenant.support_email,
        context={
            "first_name": order.tenant.trade_name,
            "order_number": order.number,
            "order_total": f"{order.currency} {order.total}",
            "order_url": f"{settings.PUBLIC_APP_URL}/admin/orders/{order.pk}",
        },
        related_type="order",
        related_id=str(order.pk),
        idempotency_key=f"staff-order:{order.pk}",
    )


def connection_for(tenant: Tenant | None) -> Any:
    """The mail connection a tenant's messages should go out on.

    ``None`` means Django's default, which is the platform's own server. A
    merchant who has filled in their own host gets a connection built from it,
    so their mail leaves from their domain and their deliverability is their
    own.

    The host is the switch: a half-filled form — a username with no server —
    must not silently produce a broken connection, so anything without a host
    falls back rather than failing.
    """
    from django.core.mail import get_connection

    row = getattr(tenant, "settings", None)
    if row is None or not row.smtp_host:
        return None

    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=row.smtp_host,
        port=row.smtp_port or 587,
        username=row.smtp_username or None,
        password=row.smtp_password or None,
        use_tls=row.smtp_use_tls,
        fail_silently=False,
    )
