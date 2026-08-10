"""
PDF rendering.

ReportLab is used rather than an HTML-to-PDF engine: it is pure Python, so the
container needs no Cairo/Pango system libraries, and the output is deterministic
enough to assert on in tests.

Documents are deliberately plain. They carry the *tenant's* trade name and
contact details, pulled from the database — never a hard-coded merchant
identity.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover
    from apps.orders.models import Order
    from apps.tenants.models import Tenant

PAGE_MARGIN = 40
BRAND_WINE = (0.482, 0.176, 0.231)  # #7B2D3B, the neutral MurasFood accent
INK = (0.18, 0.165, 0.169)
MUTED = (0.541, 0.502, 0.51)


def _styles() -> Any:
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="MuraTitle",
            parent=base["Heading1"],
            fontSize=16,
            spaceAfter=4,
            textColor="#7B2D3B",
        )
    )
    base.add(
        ParagraphStyle(
            name="MuraSubtitle",
            parent=base["Normal"],
            fontSize=9,
            textColor="#8A8082",
            spaceAfter=14,
        )
    )
    base.add(ParagraphStyle(name="MuraRight", parent=base["Normal"], alignment=TA_RIGHT))
    return base


def _document(buffer: BytesIO, title: str) -> Any:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        author="MurasFood",
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
    )


def _header(tenant: Tenant, title: str, subtitle: str) -> list[Any]:
    from reportlab.platypus import Paragraph, Spacer

    styles = _styles()
    address = ", ".join(part for part in (tenant.street, tenant.number, tenant.city) if part)
    return [
        Paragraph(tenant.trade_name, styles["MuraTitle"]),
        Paragraph(
            " · ".join(part for part in (address, tenant.phone, tenant.support_email) if part),
            styles["MuraSubtitle"],
        ),
        Paragraph(title, styles["Heading2"]),
        Paragraph(subtitle, styles["MuraSubtitle"]),
        Spacer(1, 8),
    ]


def _table(data: list[list[Any]], *, column_widths: list[float] | None = None) -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(data, colWidths=column_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(*BRAND_WINE)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.Color(0.98, 0.97, 0.97)],
                ),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.93, 0.90, 0.91)),
            ]
        )
    )
    return table


def _local_stamp(moment: datetime) -> str:
    """Format a timestamp in the active timezone for display on a document."""
    return timezone.localtime(moment).strftime("%d/%m/%Y %H:%M")


def _footer(generated_at: datetime | None = None) -> list[Any]:
    from reportlab.platypus import Paragraph, Spacer

    styles = _styles()
    stamp = (generated_at or timezone.now()).strftime("%d/%m/%Y %H:%M")
    return [
        Spacer(1, 18),
        Paragraph(f"Documento gerado automaticamente em {stamp}.", styles["MuraSubtitle"]),
    ]


def render_order_receipt(order: Order) -> bytes:
    """Render a customer receipt for one order."""
    from reportlab.platypus import Paragraph, Spacer

    buffer = BytesIO()
    document = _document(buffer, f"Recibo {order.number}")
    styles = _styles()

    story: list[Any] = _header(
        order.tenant,
        f"Recibo do pedido {order.number}",
        f"Emitido em {_local_stamp(order.placed_at or order.created_at)}",
    )

    if order.customer_name:
        story.append(Paragraph(f"<b>Cliente:</b> {order.customer_name}", styles["Normal"]))
    address = getattr(order, "address", None)
    if address is not None:
        story.append(Paragraph(f"<b>Entrega:</b> {address.one_line}", styles["Normal"]))
    story.append(Spacer(1, 10))

    rows: list[list[Any]] = [["Produto", "Qtd.", "Unitário", "Total"]]
    rows.extend(
        [
            item.product_name,
            f"{item.quantity} {item.unit_code}".strip(),
            f"{order.currency} {item.unit_price}",
            f"{order.currency} {item.line_total}",
        ]
        for item in order.items.all()
    )
    story.append(_table(rows, column_widths=[240, 70, 90, 90]))
    story.append(Spacer(1, 12))

    totals: list[list[Any]] = [["", ""], ["Subtotal", f"{order.currency} {order.subtotal}"]]
    if order.discount_total > 0:
        totals.append(["Descontos", f"- {order.currency} {order.discount_total}"])
    if order.delivery_fee > 0:
        totals.append(["Entrega", f"{order.currency} {order.delivery_fee}"])
    totals.append(["Total", f"{order.currency} {order.total}"])
    if order.refunded_total > 0:
        totals.append(["Reembolsado", f"- {order.currency} {order.refunded_total}"])

    story.append(_table(totals[1:], column_widths=[400, 90]))
    story.extend(_footer())

    document.build(story)
    return buffer.getvalue()


def render_sales_report(
    *,
    tenant: Tenant,
    period_label: str,
    summary: dict[str, Any],
    daily: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> bytes:
    """Render the sales report a merchant exports from the dashboard."""
    from reportlab.platypus import Paragraph, Spacer

    buffer = BytesIO()
    document = _document(buffer, "Relatório de vendas")
    styles = _styles()

    story: list[Any] = _header(tenant, "Relatório de vendas", period_label)

    story.append(Paragraph("Resumo", styles["Heading3"]))
    story.append(
        _table(
            [
                ["Indicador", "Valor"],
                ["Receita bruta", summary.get("gross_revenue", "0.00")],
                ["Receita líquida", summary.get("net_revenue", "0.00")],
                ["Descontos concedidos", summary.get("discount_total", "0.00")],
                ["Reembolsos", summary.get("refunded_amount", "0.00")],
                ["Pedidos", str(summary.get("order_count", 0))],
                ["Pedidos cancelados", str(summary.get("cancelled_orders", 0))],
                ["Ticket médio", summary.get("average_ticket", "0.00")],
                ["Unidades vendidas", summary.get("units_sold", "0")],
            ],
            column_widths=[300, 190],
        )
    )
    story.append(Spacer(1, 14))

    if daily:
        story.append(Paragraph("Vendas por dia", styles["Heading3"]))
        rows: list[list[Any]] = [["Data", "Pedidos", "Receita", "Ticket médio"]]
        rows.extend(
            [row["date"] or "—", str(row["orders"]), row["revenue"], row["average_ticket"]]
            for row in daily
        )
        story.append(_table(rows, column_widths=[140, 90, 130, 130]))
        story.append(Spacer(1, 14))

    if products:
        story.append(Paragraph("Produtos mais vendidos", styles["Heading3"]))
        rows = [["Produto", "Unidades", "Receita", "Margem estimada"]]
        rows.extend(
            [row["name"], row["units"], row["revenue"], row["estimated_margin"]] for row in products
        )
        story.append(_table(rows, column_widths=[210, 90, 100, 90]))

    story.extend(_footer())
    document.build(story)
    return buffer.getvalue()


def render_financial_report(
    *, tenant: Tenant, period_label: str, statement: dict[str, Any], expenses: list[dict[str, Any]]
) -> bytes:
    """Render the profit-and-loss statement."""
    from reportlab.platypus import Paragraph, Spacer

    buffer = BytesIO()
    document = _document(buffer, "Demonstrativo financeiro")
    styles = _styles()

    story: list[Any] = _header(tenant, "Demonstrativo de resultado", period_label)
    story.append(
        _table(
            [
                ["Linha", "Valor"],
                ["Receita", statement.get("revenue", "0.00")],
                ["(−) Custo das mercadorias", statement.get("cogs", "0.00")],
                ["(=) Lucro bruto", statement.get("gross_profit", "0.00")],
                ["(−) Taxas de pagamento", statement.get("payment_fees", "0.00")],
                ["(−) Custos de entrega", statement.get("delivery_costs", "0.00")],
                ["(−) Despesas operacionais", statement.get("operating_expenses", "0.00")],
                ["(−) Impostos", statement.get("taxes", "0.00")],
                ["(=) Resultado líquido", statement.get("net_result", "0.00")],
            ],
            column_widths=[300, 190],
        )
    )

    if not statement.get("expenses_recorded"):
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "Observação: nenhuma despesa operacional foi lançada no período. "
                "O resultado líquido considera apenas custos e taxas registrados "
                "automaticamente.",
                styles["MuraSubtitle"],
            )
        )

    if expenses:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Despesas por categoria", styles["Heading3"]))
        rows: list[list[Any]] = [["Categoria", "Total"]]
        rows.extend([row["category"], row["total"]] for row in expenses)
        story.append(_table(rows, column_widths=[300, 190]))

    story.extend(_footer())
    document.build(story)
    return buffer.getvalue()
