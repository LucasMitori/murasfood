"""
Monetary arithmetic.

Every amount in MurasFood is a :class:`~decimal.Decimal`. Floats are never used
for money — ``0.1 + 0.2 != 0.3`` is not an acceptable property for a financial
ledger (invariant #14).

Two precisions exist:

``MONEY_PLACES`` (2)
    Currency amounts. Rounded half-up, the convention Brazilian retail and
    accounting expect.

``QUANTITY_PLACES`` (3)
    Quantities, because bakeries and produce sell variable weight — ``1.350 kg``
    must survive a round trip.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")
PERCENT_PLACES = Decimal("0.01")

ZERO = Decimal("0.00")


def to_decimal(value: object, *, default: Decimal | None = None) -> Decimal:
    """Coerce ``value`` to :class:`Decimal` without ever going through ``float``.

    Args:
        value: Number-like input (``Decimal``, ``int``, ``str``).
        default: Returned when ``value`` cannot be parsed. When omitted an
            invalid value raises, because silently swallowing a bad amount is
            how money goes missing.

    Raises:
        ValueError: When ``value`` is unparsable and no default was supplied.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # Route through str so we get the shortest representation the user meant.
        value = repr(value)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        if default is not None:
            return default
        raise ValueError(f"Cannot interpret {value!r} as a decimal amount") from exc


def quantize_money(value: object) -> Decimal:
    """Round an amount to two decimal places using ROUND_HALF_UP."""
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def quantize_quantity(value: object) -> Decimal:
    """Round a quantity to three decimal places using ROUND_HALF_UP."""
    return to_decimal(value).quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def quantize_percent(value: object) -> Decimal:
    """Round a percentage to two decimal places."""
    return to_decimal(value).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)


def money_multiply(unit_price: object, quantity: object) -> Decimal:
    """Multiply a unit price by a quantity and round the *result* once.

    Rounding the product once — rather than rounding the operands first — keeps
    line totals consistent with what a customer computes by hand, and avoids
    accumulating a cent of drift per line across a large order.
    """
    return quantize_money(to_decimal(unit_price) * to_decimal(quantity))


def apply_percentage(amount: object, percentage: object) -> Decimal:
    """Return ``percentage`` percent of ``amount`` (e.g. 10 -> 10%)."""
    return quantize_money(to_decimal(amount) * to_decimal(percentage) / Decimal("100"))


def gross_margin(sale_price: object, cost: object) -> Decimal:
    """Absolute margin: ``sale_price - cost``."""
    return quantize_money(to_decimal(sale_price) - to_decimal(cost))


def gross_margin_percentage(sale_price: object, cost: object) -> Decimal:
    """Margin over sale price, as a percentage. Zero price yields zero."""
    price = to_decimal(sale_price)
    if price <= 0:
        return ZERO
    return quantize_percent((price - to_decimal(cost)) / price * Decimal("100"))


def markup_percentage(sale_price: object, cost: object) -> Decimal:
    """Markup over cost, as a percentage. Zero cost yields zero.

    Margin and markup are different metrics and are frequently confused: an item
    bought at 10 and sold at 20 has a 50% margin but a 100% markup.
    """
    unit_cost = to_decimal(cost)
    if unit_cost <= 0:
        return ZERO
    return quantize_percent((to_decimal(sale_price) - unit_cost) / unit_cost * Decimal("100"))


def money_str(value: object) -> str:
    """Render an amount as a two-decimal string.

    Database aggregates come back with whatever scale the backend chose —
    PostgreSQL returns ``Decimal('25.00')`` where SQLite returns
    ``Decimal('25')``. Serialising through here keeps the API's output identical
    on both, so a client parsing "25" versus "25.00" never has to care which
    database is behind it.
    """
    return f"{quantize_money(value or 0)}"


CURRENCY_SYMBOLS = {"BRL": "R$", "USD": "$", "EUR": "€"}


def money_display(value: object, currency: str = "BRL") -> str:
    """Render an amount the way a customer expects to read it.

    Deliberately separate from `money_str`, which is the wire format the API
    sends and has to stay machine-parseable. This one is for prose — order
    emails, receipts — where "BRL 24.90" is not what a Brazilian shopper reads
    on a till receipt.

    The order confirmation email said exactly that, while the merchant's
    preview of the same template showed "R$ 128,40". Nobody compared them,
    because until recently the email had no caller and was never sent.

    An unknown currency falls back to its ISO code, which is wrong-looking but
    unambiguous — better than dropping the unit from an amount of money.
    """
    amount = quantize_money(value or 0)
    code = (currency or "BRL").upper()
    symbol = CURRENCY_SYMBOLS.get(code, code)

    whole, _, cents = f"{abs(amount):.2f}".partition(".")
    sign = "-" if amount < 0 else ""

    if code == "BRL":
        # 1.234,56 — the separators are the other way round here, so this
        # cannot be left to the default formatting.
        grouped = f"{int(whole):,}".replace(",", ".")
        return f"{sign}{symbol} {grouped},{cents}"

    return f"{sign}{symbol} {int(whole):,}.{cents}"


def clamp_non_negative(value: object) -> Decimal:
    """Return ``value`` or zero, never a negative amount."""
    amount = to_decimal(value)
    return amount if amount > 0 else ZERO
