"""
PIX BR Code generation.

A malformed BR Code is rejected silently by banking apps, so the CRC and the
length prefixes are worth asserting on directly.
"""

from __future__ import annotations

from decimal import Decimal

from apps.payments.providers.pix import (
    build_br_code,
    crc16_ccitt,
    sanitize_txid,
    verify_br_code,
)


class TestCRC:
    def test_known_vector(self) -> None:
        """CRC-16/CCITT-FALSE of "123456789" is 0x29B1."""
        assert crc16_ccitt("123456789") == "29B1"

    def test_crc_changes_with_the_payload(self) -> None:
        assert crc16_ccitt("abc") != crc16_ccitt("abd")


class TestBrCode:
    def _code(self, **overrides: object) -> str:
        params = {
            "pix_key": "chave@example.test",
            "merchant_name": "Loja Alfa",
            "merchant_city": "Cidade Exemplo",
            "amount": Decimal("42.90"),
            "txid": "PEDIDO123",
        }
        params.update(overrides)
        return build_br_code(**params)  # type: ignore[arg-type]

    def test_code_is_self_verifying(self) -> None:
        assert verify_br_code(self._code()) is True

    def test_tampering_breaks_the_crc(self) -> None:
        code = self._code()
        tampered = code.replace("42.90", "00.01")
        assert verify_br_code(tampered) is False

    def test_starts_with_the_payload_format_indicator(self) -> None:
        assert self._code().startswith("000201")

    def test_contains_the_pix_domain_and_key(self) -> None:
        code = self._code()
        assert "BR.GOV.BCB.PIX" in code
        assert "chave@example.test" in code

    def test_amount_is_formatted_with_two_decimals(self) -> None:
        assert "54045.00" in self._code(amount=Decimal("5"))

    def test_currency_and_country_are_brazilian(self) -> None:
        code = self._code()
        assert "5303986" in code  # BRL
        assert "5802BR" in code

    def test_long_merchant_name_is_truncated_not_rejected(self) -> None:
        code = self._code(merchant_name="Um Nome De Loja Extremamente Longo Que Nao Cabe")
        assert verify_br_code(code) is True

    def test_accepts_a_code_without_an_amount(self) -> None:
        """Valid EMV, but never used for an order — the payer would choose."""
        code = self._code(amount=None)
        assert verify_br_code(code) is True
        assert "5406" not in code


class TestTxid:
    def test_non_alphanumeric_characters_are_stripped(self) -> None:
        assert sanitize_txid("MF-240815-ABC") == "MF240815ABC"

    def test_truncated_to_the_specification_limit(self) -> None:
        assert len(sanitize_txid("A" * 60)) == 25

    def test_empty_value_gets_a_default(self) -> None:
        assert sanitize_txid("") == "MURASFOOD"
