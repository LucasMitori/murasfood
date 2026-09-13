"""Monetary arithmetic must be exact. These tests pin that down."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.money import (
    apply_percentage,
    clamp_non_negative,
    gross_margin,
    gross_margin_percentage,
    markup_percentage,
    money_display,
    money_multiply,
    quantize_money,
    quantize_quantity,
    to_decimal,
)


class TestQuantization:
    def test_rounds_half_up_not_half_even(self) -> None:
        """Banker's rounding would turn 0.125 into 0.12; retail expects 0.13."""
        assert quantize_money("0.125") == Decimal("0.13")
        assert quantize_money("0.135") == Decimal("0.14")

    def test_quantity_keeps_three_decimals(self) -> None:
        assert quantity_str(quantize_quantity("1.3505")) == "1.351"
        assert quantity_str(quantize_quantity("1.35")) == "1.350"

    def test_float_input_does_not_leak_binary_error(self) -> None:
        # Decimal(0.1) is 0.1000000000000000055511151231257827; going through
        # repr() keeps the number the caller actually meant.
        assert to_decimal(0.1) == Decimal("0.1")

    def test_invalid_value_raises_by_default(self) -> None:
        with pytest.raises(ValueError):
            to_decimal("not-a-number")

    def test_invalid_value_can_fall_back(self) -> None:
        assert to_decimal("nonsense", default=Decimal("0")) == Decimal("0")


def quantity_str(value: Decimal) -> str:
    return f"{value:.3f}"


class TestLineTotals:
    def test_product_is_rounded_once(self) -> None:
        """Rounding the operands first would drift by a cent per line."""
        assert money_multiply("0.335", 3) == Decimal("1.01")

    def test_fractional_weight(self) -> None:
        assert money_multiply("16.50", "1.350") == Decimal("22.28")

    def test_percentage_of_amount(self) -> None:
        assert apply_percentage("100.00", "10") == Decimal("10.00")
        assert apply_percentage("33.33", "15") == Decimal("5.00")


class TestMarginMetrics:
    def test_margin_and_markup_differ(self) -> None:
        """Buy at 10, sell at 20: 50% margin, 100% markup."""
        assert gross_margin("20.00", "10.00") == Decimal("10.00")
        assert gross_margin_percentage("20.00", "10.00") == Decimal("50.00")
        assert markup_percentage("20.00", "10.00") == Decimal("100.00")

    def test_zero_cost_does_not_divide_by_zero(self) -> None:
        assert markup_percentage("20.00", "0") == Decimal("0.00")

    def test_zero_price_does_not_divide_by_zero(self) -> None:
        assert gross_margin_percentage("0", "5.00") == Decimal("0.00")

    def test_negative_margin_is_reported_not_hidden(self) -> None:
        """Selling below cost is a real situation a merchant must be able to see."""
        assert gross_margin("8.00", "10.00") == Decimal("-2.00")
        assert gross_margin_percentage("8.00", "10.00") == Decimal("-25.00")


def test_clamp_non_negative() -> None:
    assert clamp_non_negative("-5.00") == Decimal("0.00")
    assert clamp_non_negative("5.00") == Decimal("5.00")


class TestMoneyDisplay:
    """What a customer reads, as opposed to what the API sends.

    The order confirmation said "Total: BRL 24.90" while the merchant's preview
    of that same template showed "R$ 128,40". Neither was checked against the
    other, because the email had no caller and was never sent to anyone.
    """

    def test_brazilian_amounts_use_the_local_convention(self) -> None:
        assert money_display(Decimal("24.90")) == "R$ 24,90"
        # Separators are the other way round here — a thousands dot and a
        # decimal comma — which default formatting gets backwards.
        assert money_display(Decimal("1234.50")) == "R$ 1.234,50"
        assert money_display(Decimal("0")) == "R$ 0,00"

    def test_a_refund_reads_as_negative(self) -> None:
        assert money_display(Decimal("-15.50")) == "-R$ 15,50"

    def test_other_currencies_keep_their_own_convention(self) -> None:
        """Formatting dollars the Brazilian way would be its own bug."""
        assert money_display(Decimal("1234.56"), "USD") == "$ 1,234.56"

    def test_unknown_currency_keeps_its_code(self) -> None:
        """Wrong-looking but unambiguous, and never a bare number."""
        assert money_display(Decimal("9.90"), "XYZ") == "XYZ 9.90"

    def test_none_is_zero_not_a_crash(self) -> None:
        assert money_display(None) == "R$ 0,00"
