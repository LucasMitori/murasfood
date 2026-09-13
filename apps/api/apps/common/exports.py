"""
The other tables a shop needs out of the system.

Products get their own module because they go both ways — a catalogue is
imported as well as exported. These three are read-only: a merchant takes their
stock count to a spreadsheet to do a physical count against it, sends their
customer list to whoever does their mailing, and hands the accountant a month
of orders.

Each is a column list plus a function that turns a queryset into rows, so a
column added here appears in the download without any view changing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.common.spreadsheets import Column

if TYPE_CHECKING:
    from django.db.models import QuerySet

# --- Stock -------------------------------------------------------------------

INVENTORY_COLUMNS: list[Column] = [
    Column("sku", "SKU", "ARROZ-5KG"),
    Column("name", "Produto", "Arroz Tipo 1 5kg"),
    Column("unit", "Unidade", "pct"),
    Column("quantity", "Em estoque", "30"),
    Column("reserved", "Reservado", "3"),
    Column("available", "Disponivel", "27"),
    Column("minimum", "Estoque minimo", "5"),
    Column("reorder", "Ponto de recompra", "10"),
    Column("location", "Localizacao", "Corredor 3"),
]


def inventory_rows(queryset: QuerySet) -> list[dict[str, Any]]:
    return [
        {
            "sku": item.product.sku,
            "name": item.product.name,
            "unit": item.product.sale_unit.code if item.product.sale_unit else "",
            "quantity": item.quantity,
            "reserved": item.reserved_quantity,
            # Derived rather than stored, and the number the shopkeeper acts on:
            # what is on the shelf minus what is already promised to an order.
            "available": item.quantity - item.reserved_quantity,
            "minimum": item.minimum_stock,
            "reorder": item.reorder_threshold,
            "location": item.location,
        }
        for item in queryset
    ]


# --- Customers ---------------------------------------------------------------

CUSTOMER_COLUMNS: list[Column] = [
    Column("name", "Nome", "Maria Silva"),
    Column("email", "E-mail", "maria@exemplo.com"),
    Column("phone", "Telefone", "(11) 90000-0000"),
    Column("orders", "Pedidos", "12"),
    Column("created_at", "Cliente desde", "01/02/2026"),
]


def customer_rows(queryset: QuerySet) -> list[dict[str, Any]]:
    return [
        {
            "name": customer.get_full_name() or "",
            "email": customer.email,
            "phone": customer.phone,
            "orders": getattr(customer, "order_count", ""),
            "created_at": customer.created_at.strftime("%d/%m/%Y"),
        }
        for customer in queryset
    ]


# --- Orders ------------------------------------------------------------------

ORDER_COLUMNS: list[Column] = [
    Column("number", "Pedido", "MF-260101-ABC123"),
    Column("placed_at", "Data", "01/02/2026 14:30"),
    Column("customer", "Cliente", "Maria Silva"),
    Column("status", "Situacao", "PAID"),
    Column("delivery_method", "Entrega", "PICKUP"),
    Column("items", "Itens", "5"),
    Column("subtotal", "Subtotal", "128,40"),
    Column("discount", "Descontos", "0,00"),
    Column("delivery_fee", "Taxa de entrega", "0,00"),
    Column("total", "Total", "128,40"),
]


def order_rows(queryset: QuerySet) -> list[dict[str, Any]]:
    return [
        {
            "number": order.number,
            # The shop's own clock: an accountant reconciling a month does not
            # want to convert UTC in their head.
            "placed_at": _local(order.placed_at or order.created_at),
            "customer": order.customer_name or (order.customer.email if order.customer else ""),
            "status": order.status,
            "delivery_method": order.delivery_method,
            "items": order.items.count(),
            "subtotal": order.subtotal,
            "discount": order.discount_total,
            "delivery_fee": order.delivery_fee,
            "total": order.total,
        }
        for order in queryset
    ]


def _local(value: Any) -> str:
    from django.utils import timezone

    if value is None:
        return ""
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")
