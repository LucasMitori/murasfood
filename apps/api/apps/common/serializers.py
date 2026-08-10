"""Serializer helpers shared across domains."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from .money import MONEY_PLACES, QUANTITY_PLACES


class MoneySerializerField(serializers.DecimalField):
    """A currency amount.

    Always serialised as a string ("12.90") — JSON numbers are IEEE-754 doubles
    in most clients, and `0.1 + 0.2` must not become a price.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("min_value", Decimal("0"))
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class QuantitySerializerField(serializers.DecimalField):
    """A quantity with three decimals, so 1.350 kg survives a round trip."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 3)
        kwargs.setdefault("min_value", Decimal("0"))
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class ErrorDetailSerializer(serializers.Serializer):
    """Documents the error envelope for OpenAPI consumers."""

    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)
    request_id = serializers.CharField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()


class MessageResponseSerializer(serializers.Serializer):
    """Generic acknowledgement payload."""

    detail = serializers.CharField()


def round_money(value: Any) -> Decimal:
    """Quantize to currency precision. Convenience for serializer methods."""
    return Decimal(str(value)).quantize(MONEY_PLACES)


def round_quantity(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(QUANTITY_PLACES)
