"""
Financial models.

One ledger table (:class:`FinancialTransaction`) rather than separate Expense,
RevenueEntry and PaymentFee tables. They differ only by sign and category, and a
single ledger means the profit-and-loss report is one query instead of three
unions that can silently disagree.

Entries are soft-deleted, never removed: a financial record that can vanish is
not a financial record (invariant #9).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TenantOwnedModel


class AccountType(models.TextChoices):
    CASH = "CASH", _("Cash")
    BANK = "BANK", _("Bank account")
    CARD = "CARD", _("Card acquirer")
    OTHER = "OTHER", _("Other")


class TransactionType(models.TextChoices):
    REVENUE = "REVENUE", _("Revenue")
    EXPENSE = "EXPENSE", _("Expense")


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    SETTLED = "SETTLED", _("Settled")
    CANCELLED = "CANCELLED", _("Cancelled")


class CategoryKind(models.TextChoices):
    """What a category contributes to the result.

    ``COGS`` is separate from a general expense because gross profit is
    ``revenue − COGS``; lumping the two together makes margin meaningless.
    """

    SALES = "SALES", _("Sales revenue")
    OTHER_REVENUE = "OTHER_REVENUE", _("Other revenue")
    COGS = "COGS", _("Cost of goods sold")
    OPERATING_EXPENSE = "OPERATING_EXPENSE", _("Operating expense")
    PAYMENT_FEE = "PAYMENT_FEE", _("Payment fees")
    DELIVERY_COST = "DELIVERY_COST", _("Delivery costs")
    TAX = "TAX", _("Taxes")


#: Categories created for every tenant, so a merchant has a usable chart of
#: accounts from day one.
DEFAULT_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("sales", "Vendas", CategoryKind.SALES),
    ("delivery-income", "Taxa de entrega", CategoryKind.OTHER_REVENUE),
    ("cogs", "Custo das mercadorias", CategoryKind.COGS),
    ("payment-fees", "Taxas de pagamento", CategoryKind.PAYMENT_FEE),
    ("delivery-costs", "Custos de entrega", CategoryKind.DELIVERY_COST),
    ("payroll", "Folha de pagamento", CategoryKind.OPERATING_EXPENSE),
    ("rent", "Aluguel", CategoryKind.OPERATING_EXPENSE),
    ("utilities", "Água, luz e internet", CategoryKind.OPERATING_EXPENSE),
    ("supplies", "Materiais e insumos", CategoryKind.OPERATING_EXPENSE),
    ("marketing", "Marketing", CategoryKind.OPERATING_EXPENSE),
    ("taxes", "Impostos", CategoryKind.TAX),
    ("other", "Outros", CategoryKind.OPERATING_EXPENSE),
)


class FinancialAccount(TenantOwnedModel):
    """Where money sits: the till, a bank account, an acquirer balance."""

    name = models.CharField(_("name"), max_length=120)
    account_type = models.CharField(
        _("type"), max_length=12, choices=AccountType.choices, default=AccountType.BANK
    )
    opening_balance = models.DecimalField(
        _("opening balance"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    is_default = models.BooleanField(_("default"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("financial account")
        verbose_name_plural = _("financial accounts")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_default=True),
                name="uniq_default_financial_account",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class FinancialCategory(TenantOwnedModel):
    """A line in the chart of accounts."""

    code = models.SlugField(_("code"), max_length=48)
    name = models.CharField(_("name"), max_length=120)
    kind = models.CharField(_("kind"), max_length=20, choices=CategoryKind.choices)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("financial category")
        verbose_name_plural = _("financial categories")
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uniq_financial_category_tenant_code"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def transaction_type(self) -> str:
        """Whether entries in this category add to or subtract from the result."""
        return (
            TransactionType.REVENUE
            if self.kind in {CategoryKind.SALES, CategoryKind.OTHER_REVENUE}
            else TransactionType.EXPENSE
        )


class FinancialTransaction(TenantOwnedModel, SoftDeleteModel):
    """One ledger entry.

    ``amount`` is always positive; direction comes from ``transaction_type``.
    Mixing signed amounts with a type field is how ledgers end up double-negating
    a refund.
    """

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("account"),
    )
    category = models.ForeignKey(
        FinancialCategory,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("category"),
    )
    transaction_type = models.CharField(_("type"), max_length=10, choices=TransactionType.choices)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=TransactionStatus.choices,
        default=TransactionStatus.SETTLED,
    )

    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2)
    occurred_on = models.DateField(
        _("date"),
        db_index=True,
        help_text=_("Business date in the tenant's timezone, not the server's."),
    )
    description = models.CharField(_("description"), max_length=255)
    note = models.TextField(_("note"), blank=True)

    reference_type = models.CharField(_("reference type"), max_length=32, blank=True)
    reference_id = models.CharField(_("reference id"), max_length=64, blank=True, db_index=True)

    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("financial transaction")
        verbose_name_plural = _("financial transactions")
        ordering = ["-occurred_on", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="financial_amount_positive"
            ),
            # An order's revenue is recorded once, no matter how many times the
            # projection job runs.
            models.UniqueConstraint(
                fields=["tenant", "reference_type", "reference_id", "category"],
                condition=~models.Q(reference_id=""),
                name="uniq_financial_entry_per_reference_category",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "occurred_on"]),
            models.Index(fields=["tenant", "transaction_type", "occurred_on"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"{self.transaction_type} {self.amount} — {self.description}"

    @property
    def signed_amount(self) -> Decimal:
        """Positive for revenue, negative for expenses."""
        return self.amount if self.transaction_type == TransactionType.REVENUE else -self.amount
