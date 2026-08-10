"""Finance serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .models import FinancialAccount, FinancialCategory, FinancialTransaction


class FinancialAccountSerializer(serializers.ModelSerializer):
    opening_balance = MoneySerializerField(required=False)

    class Meta:
        model = FinancialAccount
        fields = ["id", "name", "account_type", "opening_balance", "is_default", "is_active"]
        read_only_fields = ["id"]


class FinancialCategorySerializer(serializers.ModelSerializer):
    transaction_type = serializers.CharField(read_only=True)

    class Meta:
        model = FinancialCategory
        fields = ["id", "code", "name", "kind", "parent", "transaction_type", "is_active"]
        read_only_fields = ["id", "transaction_type"]


class FinancialTransactionSerializer(serializers.ModelSerializer):
    amount = MoneySerializerField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = FinancialTransaction
        fields = [
            "id",
            "account",
            "account_name",
            "category",
            "category_name",
            "transaction_type",
            "status",
            "amount",
            "occurred_on",
            "description",
            "note",
            "reference_type",
            "reference_id",
            "created_at",
        ]
        read_only_fields = ["id", "reference_type", "reference_id", "created_at"]


class ExpenseCreateSerializer(serializers.Serializer):
    """Manual expense entry."""

    category_code = serializers.CharField(max_length=48)
    amount = MoneySerializerField()
    occurred_on = serializers.DateField()
    description = serializers.CharField(max_length=255)


class ProfitAndLossSerializer(serializers.Serializer):
    """Documents the P&L payload for OpenAPI consumers."""

    period = serializers.DictField()
    revenue = serializers.CharField()
    sales_revenue = serializers.CharField()
    other_revenue = serializers.CharField()
    cogs = serializers.CharField()
    gross_profit = serializers.CharField()
    gross_margin_percentage = serializers.CharField()
    payment_fees = serializers.CharField()
    delivery_costs = serializers.CharField()
    operating_expenses = serializers.CharField()
    taxes = serializers.CharField()
    total_expenses = serializers.CharField()
    net_result = serializers.CharField()
    expenses_recorded = serializers.BooleanField()
