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

#: Brand colours, kept in step with the storefront theme
#: (``apps/web/app/utils/theme.ts``). Email clients strip CSS custom properties
#: and most external stylesheets, so every value here is inlined by hand.
BRAND = "#8C1425"
BRAND_DARK = "#6D0E1B"
INK = "#1F1C1D"
MUTED = "#57504F"
PAPER = "#F6F4F3"
LINE = "#E2DBDA"

_LAYOUT = """<!doctype html>
<html lang="{{ locale }}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{{ subject }}</title>
  </head>
  <body style="margin:0;padding:0;background:__PAPER__;">
    <!-- Preheader: the grey line a client shows beside the subject. Hidden in
         the body itself, or it would repeat the first paragraph twice. -->
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{{ preheader }}</div>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:__PAPER__;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="max-width:560px;background:#FFFFFF;border:1px solid __LINE__;
                        border-radius:16px;overflow:hidden;">
            <tr>
              <td style="background:__BRAND__;padding:20px 32px;">
                <p style="margin:0;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
                          font-size:17px;font-weight:700;color:#FFFFFF;letter-spacing:-0.01em;">
                  {{ store_name }}
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
                         font-size:15px;line-height:1.6;color:__INK__;">
                {{ content }}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 28px;border-top:1px solid __LINE__;
                         font-family:system-ui,-apple-system,'Segoe UI',sans-serif;">
                <p style="margin:0;font-size:12px;line-height:1.5;color:__MUTED__;">
                  {{ store_name }} &middot;
                  <a href="mailto:{{ support_email }}" style="color:__MUTED__;">{{ support_email }}</a>
                </p>
                <p style="margin:8px 0 0;font-size:11px;color:__MUTED__;">
                  Você recebeu este e-mail porque tem uma conta em {{ store_name }}.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

_LAYOUT = (
    _LAYOUT.replace("__BRAND__", BRAND)
    .replace("__PAPER__", PAPER)
    .replace("__LINE__", LINE)
    .replace("__INK__", INK)
    .replace("__MUTED__", MUTED)
)


def button(label: str, url: str) -> str:
    """A call to action that survives Outlook.

    Rendered as a table rather than a styled anchor: Word's rendering engine,
    which Outlook on Windows uses, drops padding on inline-block links and the
    button collapses to bare underlined text.
    """
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:20px 0;"><tr><td align="center" '
        f'style="background:{BRAND};border-radius:10px;">'
        f'<a href="{url}" style="display:inline-block;padding:13px 26px;'
        'font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;font-size:15px;'
        'font-weight:600;color:#FFFFFF;text-decoration:none;">'
        f'{label}</a></td></tr></table>'
    )


def note(text: str) -> str:
    """Small print under the main message."""
    return f'<p style="margin:0;font-size:13px;color:{MUTED};">{text}</p>'


def panel(rows: str) -> str:
    """A tinted block for the facts of an order — number, total, status."""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:20px 0;background:{PAPER};border-radius:12px;">'
        f'<tr><td style="padding:16px 20px;font-size:14px;color:{INK};">{rows}</td></tr></table>'
    )


def row(label: str, value: str) -> str:
    return (
        f'<p style="margin:0 0 6px;font-size:13px;color:{MUTED};">{label}<br>'
        f'<strong style="font-size:15px;color:{INK};">{value}</strong></p>'
    )


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
            + button("Confirmar e-mail", "{{ verification_url }}")
            + note("O link expira em {{ expires_in_hours }} horas. "
                   "Se não foi você quem criou a conta, ignore este e-mail.")
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
            + button("Criar nova senha", "{{ reset_url }}")
            + note("O link expira em {{ expires_in_hours }} horas. "
                   "Se não foi você, ignore este e-mail e sua senha continuará a mesma.")
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
            "<p>Recebemos seu pedido e já estamos cuidando dele.</p>"
            + panel(row("Pedido", "{{ order_number }}") + row("Total", "{{ order_total }}"))
            + button("Acompanhar pedido", "{{ order_url }}")
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
            "<p>Seu pagamento foi confirmado. Já começamos a separar tudo.</p>"
            + panel(row("Pedido", "{{ order_number }}") + row("Pago", "{{ order_total }}"))
            + button("Acompanhar pedido", "{{ order_url }}")
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
