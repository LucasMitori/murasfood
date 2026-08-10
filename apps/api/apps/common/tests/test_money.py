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
