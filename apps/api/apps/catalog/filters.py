"""Catalog filters.

Price filtering works on the ``effective_price`` annotation, so "under R$10"
respects an active promotion rather than the base price.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import F, Q, QuerySet
from django_filters import rest_framework as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(method="filter_category")
    brand = filters.CharFilter(field_name="brand__slug", lookup_expr="iexact")
    tag = filters.CharFilter(field_name="tags__slug", lookup_expr="iexact")
    min_price = filters.NumberFilter(field_name="effective_price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="effective_price", lookup_expr="lte")
    is_featured = filters.BooleanFilter()
    on_sale = filters.BooleanFilter(method="filter_on_sale")
    in_stock = filters.BooleanFilter(method="filter_in_stock")
    availability = filters.CharFilter(method="filter_availability")
    min_discount = filters.NumberFilter(method="filter_min_discount")

    class Meta:
        model = Product
        fields = ["category", "brand", "tag", "is_featured", "product_type"]

    def filter_category(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Accept a slug or an id, and include the category's children.

        A shopper browsing "Bakery" expects to see items filed under
        "Bakery › Bread" too.
        """
        from .models import Category

        lookup = Q(slug=value)
        if _looks_like_uuid(value):
            lookup |= Q(pk=value)

        category = Category.objects.filter(lookup, tenant_id=self._tenant_id()).first()
        if category is None:
            return queryset.none()

        ids = [category.pk, *category.children.values_list("pk", flat=True)]
        return queryset.filter(category_id__in=ids)

    def filter_on_sale(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        if not value:
            return queryset
        return queryset.filter(sale_price__isnull=False, sale_price__lt=F("base_price"))

    def filter_in_stock(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        """Products a customer can actually buy right now.

        Untracked products (fresh bakery batches) always count as in stock.
        """
        if not value:
            return queryset
        return queryset.filter(
            Q(inventory__isnull=True)
            | Q(inventory__track_stock=False)
            | Q(inventory__quantity__gt=F("inventory__reserved_quantity"))
        )

    def filter_availability(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Split the catalogue by whether it can be bought right now.

        `in_stock=true` already existed but has no opposite: a boolean filter
        reads `false` as "do not filter", so there was no way to ask for the
        shelf gaps. The shop needs that view — it is where the
        "tell me when it is back" button lives, and where a merchant looks to
        decide what to reorder.
        """
        choice = (value or "").strip().lower()
        if choice == "in":
            return self.filter_in_stock(queryset, name, True)
        if choice == "out":
            return queryset.filter(
                inventory__track_stock=True,
                inventory__quantity__lte=F("inventory__reserved_quantity"),
            )
        return queryset

    def filter_min_discount(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """Products at least ``value`` percent off.

        Expressed against the *base* price, which is the number the shopper is
        comparing against — a discount measured off an already-discounted price
        would let "50% off" mean anything.
        """
        try:
            percent = Decimal(str(value))
        except (TypeError, ArithmeticError):
            return queryset
        if percent <= 0:
            return queryset

        factor = (Decimal("100") - percent) / Decimal("100")
        return queryset.filter(
            sale_price__isnull=False,
            sale_price__lte=F("base_price") * factor,
        )

    def _tenant_id(self) -> Any:
        request = getattr(self, "request", None)
        return getattr(request, "tenant_id", None)


def _looks_like_uuid(value: str) -> bool:
    stripped = value.replace("-", "")
    return len(stripped) == 32 and all(c in "0123456789abcdefABCDEF" for c in stripped)
