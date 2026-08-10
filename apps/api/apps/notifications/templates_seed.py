"""
Default email templates.

Seeded per tenant so a merchant can edit the wording immediately. The copy is
intentionally generic — no merchant name, no address, no branding beyond the
``{{ store_name }}`` placeholder — because the codebase must contain nothing
identifying a specific business (spec §66).

Placeholders use ``{{ name }}`` and are substituted literally; see
:func:`apps.notifications.services.render_template`.
"""

from __future__ import annotations

from typing import Any

_LAYOUT = """<!doctype html>
<html lang="{{ locale }}">
  <head><meta charset="utf-8"><title>{{ subject }}</title></head>
  <body style="margin:0;padding:24px;background:#FAF7F7;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#2E2A2B;">
    <table role="presentation" style="max-width:560px;margin:0 auto;background:#FFFFFF;border-radius:12px;padding:32px;">
      <tr><td>
        <h1 style="margin:0 0 16px;font-size:20px;color:#7B2D3B;">{{ store_name }}</h1>
        {{ content }}
        <hr style="border:none;border-top:1px solid #EEE6E7;margin:28px 0;">
        <p style="font-size:12px;color:#8A8082;margin:0;">
          {{ store_name }} · {{ support_email }}
        </p>
      </td></tr>
    </table>
  </body>
</html>"""


def _wrap(content: str) -> str:
    return _LAYOUT.replace("{{ content }}", content)


DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "key": "account.verify",
        "subject": "Confirme seu e-mail",
        "variables": ["first_name", "verification_url", "expires_in_hours"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Confirme seu endereço de e-mail para ativar sua conta.</p>"
            '<p><a href="{{ verification_url }}" '
            'style="display:inline-block;background:#7B2D3B;color:#fff;padding:12px 20px;'
            'border-radius:8px;text-decoration:none;">Confirmar e-mail</a></p>'
            '<p style="font-size:13px;color:#8A8082;">O link expira em {{ expires_in_hours }} horas.</p>'
        ),
        "text": (
            "Olá, {{ first_name }}!\n\n"
            "Confirme seu e-mail: {{ verification_url }}\n"
            "O link expira em {{ expires_in_hours }} horas."
        ),
    },
    {
        "key": "account.welcome",
        "subject": "Bem-vindo(a)!",
        "variables": ["first_name"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p><p>Sua conta está ativa. Bom apetite e boas compras.</p>"
        ),
        "text": "Olá, {{ first_name }}!\n\nSua conta está ativa.",
    },
    {
        "key": "account.password_reset",
        "subject": "Redefinição de senha",
        "variables": ["first_name", "reset_url", "expires_in_hours"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Recebemos um pedido para redefinir sua senha.</p>"
            '<p><a href="{{ reset_url }}" '
            'style="display:inline-block;background:#7B2D3B;color:#fff;padding:12px 20px;'
            'border-radius:8px;text-decoration:none;">Criar nova senha</a></p>'
            '<p style="font-size:13px;color:#8A8082;">O link expira em {{ expires_in_hours }} horas. '
            "Se não foi você, ignore este e-mail.</p>"
        ),
        "text": (
            "Olá, {{ first_name }}!\n\n"
            "Redefina sua senha: {{ reset_url }}\n"
            "O link expira em {{ expires_in_hours }} horas."
        ),
    },
    {
        "key": "order.created",
        "subject": "Pedido {{ order_number }} recebido",
        "variables": ["first_name", "order_number", "order_total", "order_url"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Recebemos seu pedido <strong>{{ order_number }}</strong>.</p>"
            "<p>Total: <strong>{{ order_total }}</strong></p>"
            '<p><a href="{{ order_url }}">Acompanhar pedido</a></p>'
        ),
        "text": (
            "Olá, {{ first_name }}!\n\n"
            "Pedido {{ order_number }} recebido. Total: {{ order_total }}.\n"
            "{{ order_url }}"
        ),
    },
    {
        "key": "order.payment_confirmed",
        "subject": "Pagamento confirmado — pedido {{ order_number }}",
        "variables": ["first_name", "order_number", "order_total", "order_url"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Seu pagamento de <strong>{{ order_total }}</strong> foi confirmado.</p>"
            "<p>Já estamos preparando o pedido {{ order_number }}.</p>"
            '<p><a href="{{ order_url }}">Acompanhar pedido</a></p>'
        ),
        "text": (
            "Olá, {{ first_name }}!\n\n"
            "Pagamento confirmado para o pedido {{ order_number }}.\n{{ order_url }}"
        ),
    },
    {
        "key": "order.preparing",
        "subject": "Pedido {{ order_number }} em preparação",
        "variables": ["first_name", "order_number", "order_url"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p><p>Estamos preparando seu pedido {{ order_number }}.</p>"
        ),
        "text": "Estamos preparando seu pedido {{ order_number }}.",
    },
    {
        "key": "order.ready",
        "subject": "Pedido {{ order_number }} pronto para retirada",
        "variables": ["first_name", "order_number", "order_url"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Seu pedido {{ order_number }} está pronto para retirada.</p>"
        ),
        "text": "Seu pedido {{ order_number }} está pronto para retirada.",
    },
    {
        "key": "order.out_for_delivery",
        "subject": "Pedido {{ order_number }} saiu para entrega",
        "variables": ["first_name", "order_number", "order_url"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p><p>Seu pedido {{ order_number }} saiu para entrega.</p>"
        ),
        "text": "Seu pedido {{ order_number }} saiu para entrega.",
    },
    {
        "key": "order.delivered",
        "subject": "Pedido {{ order_number }} entregue",
        "variables": ["first_name", "order_number"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p><p>Seu pedido {{ order_number }} foi entregue. Obrigado!</p>"
        ),
        "text": "Seu pedido {{ order_number }} foi entregue.",
    },
    {
        "key": "order.cancelled",
        "subject": "Pedido {{ order_number }} cancelado",
        "variables": ["first_name", "order_number", "reason"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>Seu pedido {{ order_number }} foi cancelado.</p>"
            "<p>{{ reason }}</p>"
        ),
        "text": "Seu pedido {{ order_number }} foi cancelado. {{ reason }}",
    },
    {
        "key": "order.refunded",
        "subject": "Reembolso do pedido {{ order_number }}",
        "variables": ["first_name", "order_number", "order_total"],
        "html": _wrap(
            "<p>Olá, {{ first_name }}!</p>"
            "<p>O reembolso do pedido {{ order_number }} foi processado.</p>"
        ),
        "text": "O reembolso do pedido {{ order_number }} foi processado.",
    },
    {
        "key": "inventory.low_stock",
        "subject": "Alerta de estoque baixo",
        "variables": ["count", "items"],
        "html": _wrap(
            "<p>{{ count }} item(ns) estão abaixo do estoque mínimo.</p>"
            "<p>Acesse o painel para repor.</p>"
        ),
        "text": "{{ count }} item(ns) com estoque baixo.",
    },
)

#: Order status -> template key. Statuses missing from this map send no email —
#: customers should not be notified about internal bookkeeping transitions.
ORDER_STATUS_TEMPLATES: dict[str, str] = {
    "PENDING_PAYMENT": "order.created",
    "PAID": "order.payment_confirmed",
    "PREPARING": "order.preparing",
    "READY_FOR_PICKUP": "order.ready",
    "OUT_FOR_DELIVERY": "order.out_for_delivery",
    "DELIVERED": "order.delivered",
    "CANCELLED": "order.cancelled",
    "REFUNDED": "order.refunded",
}
