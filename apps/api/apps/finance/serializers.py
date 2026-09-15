"""Finance serializers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.common.serializers import MoneySerializerField

from .models import (
    Budget,
    BudgetLine,
    FinancialAccount,
    FinancialCategory,
    FinancialTransaction,
)


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


class BudgetLineSerializer(serializers.ModelSerializer):
    planned_amount = MoneySerializerField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_kind = serializers.CharField(source="category.kind", read_only=True)

    class Meta:
        model = BudgetLine
        fields = [
            "id",
            "category",
            "category_name",
            "category_kind",
            "planned_amount",
            "note",
        ]
        read_only_fields = ["id", "category_name", "category_kind"]


class BudgetSerializer(serializers.ModelSerializer):
    """A month's plan, written and read as one object.

    Lines are nested and replaced wholesale on write. A budget is edited as a
    sheet — the merchant changes four numbers and saves — so a PATCH per line
    would mean four requests that can half-succeed, leaving a plan that was
    never anyone's intention.
    """

    lines = BudgetLineSerializer(many=True, required=False)
    period = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id",
            "name",
            "year",
            "month",
            "note",
            "is_active",
            "lines",
            "period",
            "created_at",
        ]
        read_only_fields = ["id", "period", "created_at"]

    def get_period(self, obj: Budget) -> dict[str, str]:
        start, end = obj.period
        return {"start": start.isoformat(), "end": end.isoformat()}

    def validate_month(self, value: int) -> int:
        if not 1 <= value <= 12:
            raise serializers.ValidationError(_("The month must be between 1 and 12."))
        return value

    def validate_year(self, value: int) -> int:
        # Wide enough for any plausible plan, narrow enough that a typo in the
        # year field does not create a budget for the year 202.
        if not 2000 <= value <= 2100:
            raise serializers.ValidationError(_("That year is out of range."))
        return value

    def _write_lines(self, budget: Budget, lines: list[dict[str, Any]]) -> None:
        """Replace the plan's lines with exactly what was sent.

        Categories are re-checked against the budget's own tenant: the field
        would otherwise accept any category id in the database, which is a
        cross-tenant write through a foreign key.
        """
        from .models import FinancialCategory

        allowed = set(
            FinancialCategory.objects.filter(tenant_id=budget.tenant_id).values_list(
                "pk", flat=True
            )
        )

        budget.lines.all().delete()
        BudgetLine.objects.bulk_create(
            [
                BudgetLine(
                    tenant_id=budget.tenant_id,
                    budget=budget,
                    category=line["category"],
                    planned_amount=line.get("planned_amount") or 0,
                    note=line.get("note", "")[:255],
                )
                for line in lines
                if line.get("category") is not None and line["category"].pk in allowed
            ]
        )

    def create(self, validated_data: dict[str, Any]) -> Budget:
        lines = validated_data.pop("lines", [])
        budget = Budget.objects.create(**validated_data)
        self._write_lines(budget, lines)
        return budget

    def update(self, instance: Budget, validated_data: dict[str, Any]) -> Budget:
        lines = validated_data.pop("lines", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if lines is not None:
            self._write_lines(instance, lines)
        return instance


class PriceSimulationSerializer(serializers.Serializer):
    """Inputs for the "what if I raised prices" question."""

    change_percentage = serializers.DecimalField(max_digits=6, decimal_places=2)
    elasticity = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text=(
            "How much volume moves per 1% of price, as a negative number. "
            "Defaults to -0.8 for a mixed grocery basket."
        ),
    )
    category = serializers.UUIDField(required=False, allow_null=True)

    def validate_change_percentage(self, value: Decimal) -> Decimal:
        # A simulation outside this band is extrapolating a linear model far
        # past where it means anything.
        if not Decimal("-90") <= value <= Decimal("200"):
            raise serializers.ValidationError(_("Use a change between -90% and 200%."))
        return value

    def validate_elasticity(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value > 0:
            raise serializers.ValidationError(
                _("Elasticity is negative: raising a price lowers volume.")
            )
        if value < Decimal("-10"):
            raise serializers.ValidationError(_("That elasticity is implausible."))
        return value
