"""
PIX BR Code generation.

Builds the EMV®QRCPS payload the Central Bank standardises for PIX — the same
string a customer pastes into their banking app ("copia e cola") and the content
encoded in the QR image.

Structure: a sequence of ``ID | length | value`` triplets, ending with a CRC-16
over everything that precedes it. Getting the length prefixes or the CRC wrong
produces a code that every bank app silently rejects, so both are covered by
tests.

Reference: EMV QR Code Specification for Payment Systems (merchant-presented),
as profiled by BCB for PIX.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

PAYLOAD_FORMAT_INDICATOR: Final = "00"
POINT_OF_INITIATION: Final = "01"
MERCHANT_ACCOUNT_INFORMATION: Final = "26"
MERCHANT_CATEGORY_CODE: Final = "52"
TRANSACTION_CURRENCY: Final = "53"
TRANSACTION_AMOUNT: Final = "54"
COUNTRY_CODE: Final = "58"
MERCHANT_NAME: Final = "59"
MERCHANT_CITY: Final = "60"
ADDITIONAL_DATA: Final = "62"
CRC: Final = "63"

PIX_GUI: Final = "BR.GOV.BCB.PIX"
BRL_CURRENCY_CODE: Final = "986"

#: Field length caps from the specification. Exceeding them makes the code
#: unreadable rather than merely ugly, so values are truncated on the way in.
MAX_MERCHANT_NAME = 25
MAX_MERCHANT_CITY = 15
MAX_TXID = 25


def _field(field_id: str, value: str) -> str:
    """Encode one ``ID | length | value`` triplet."""
    return f"{field_id}{len(value):02d}{value}"


def crc16_ccitt(payload: str) -> str:
    """CRC-16/CCITT-FALSE over ``payload``, as four uppercase hex digits.

    Polynomial 0x1021, initial value 0xFFFF, no reflection, no final XOR — the
    exact variant the PIX specification requires.
    """
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _sanitize(value: str, limit: int) -> str:
    """Strip characters banks reject, upper-case, and truncate."""
    allowed = "".join(ch for ch in (value or "").upper() if ch.isalnum() or ch in " .-").strip()
    return allowed[:limit] or "N/A"


def sanitize_txid(value: str) -> str:
    """Transaction ids are alphanumeric, at most 25 characters."""
    cleaned = "".join(ch for ch in (value or "") if ch.isalnum())
    return (cleaned[:MAX_TXID] or "MURASFOOD").upper()


def build_br_code(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount: Decimal | None = None,
    txid: str = "",
    description: str = "",
    is_dynamic: bool = True,
) -> str:
    """Assemble a complete BR Code string.

    Args:
        pix_key: The merchant's PIX key (CPF/CNPJ, email, phone or random key).
        amount: When omitted the payer chooses the amount — never do that for an
            order, or a customer can pay one cent for a full basket.
        txid: Correlates the payment back to our record when the bank reports it.

    Returns:
        The copy-and-paste payload, CRC included.
    """
    account_info = _field("00", PIX_GUI) + _field("01", pix_key.strip())
    if description:
        account_info += _field("02", _sanitize(description, 40))

    parts = [
        _field(PAYLOAD_FORMAT_INDICATOR, "01"),
    ]
    if is_dynamic:
        # "12" marks a single-use code; "11" would allow repeated payment.
        parts.append(_field(POINT_OF_INITIATION, "12"))

    parts.extend(
        [
            _field(MERCHANT_ACCOUNT_INFORMATION, account_info),
            _field(MERCHANT_CATEGORY_CODE, "0000"),
            _field(TRANSACTION_CURRENCY, BRL_CURRENCY_CODE),
        ]
    )

    if amount is not None:
        parts.append(_field(TRANSACTION_AMOUNT, f"{Decimal(amount):.2f}"))

    parts.extend(
        [
            _field(COUNTRY_CODE, "BR"),
            _field(MERCHANT_NAME, _sanitize(merchant_name, MAX_MERCHANT_NAME)),
            _field(MERCHANT_CITY, _sanitize(merchant_city, MAX_MERCHANT_CITY)),
            _field(ADDITIONAL_DATA, _field("05", sanitize_txid(txid) if txid else "***")),
        ]
    )

    payload = "".join(parts) + f"{CRC}04"
    return payload + crc16_ccitt(payload)


def verify_br_code(payload: str) -> bool:
    """Check a BR Code's CRC. Useful in tests and when importing codes."""
    if len(payload) < 8 or payload[-8:-4] != f"{CRC}04":
        return False
    return crc16_ccitt(payload[:-4]) == payload[-4:].upper()


def render_qr_code_base64(payload: str) -> str:
    """Render a BR Code as a base64 PNG data payload.

    Returns an empty string when the optional ``qrcode`` dependency is missing:
    the copy-and-paste string alone is enough to complete a payment, so a
    missing image must not fail checkout.
    """
    try:
        import base64
        from io import BytesIO

        import qrcode

        image = qrcode.make(payload)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return ""
