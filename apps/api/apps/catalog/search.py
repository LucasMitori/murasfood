"""
Product search.

PostgreSQL full-text plus trigram similarity is enough for a catalog of tens of
thousands of products; Elasticsearch is not introduced until it demonstrably is
not (spec §37).

The implementation degrades gracefully: on PostgreSQL it ranks by full-text
relevance and fuzzy name similarity, and on any other backend (the SQLite used
for a zero-dependency test run) it falls back to case-insensitive matching. The
same function therefore works everywhere, and tests do not need a database
server to be meaningful.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import connection
from django.db.models import Q, Value
from django.db.models.functions import Greatest

if TYPE_CHECKING:  # pragma: no cover
    from django.db.models import QuerySet

#: Below this trigram similarity a "match" is noise rather than a typo.
SIMILARITY_THRESHOLD = 0.15

#: Fields searched, in descending order of how much a hit should count.
SEARCH_FIELDS = ("name", "short_description", "description", "sku")


def is_postgres() -> bool:
    return connection.vendor == "postgresql"


def normalise_term(term: str) -> str:
    """Trim and bound a user-supplied query.

    An unbounded term is a cheap way to make the database do expensive work.
    """
    return (term or "").strip()[:120]


def _fallback_search(queryset: QuerySet, term: str) -> QuerySet:
    """Portable ``icontains`` search used outside PostgreSQL."""
    filters = Q()
    for field in SEARCH_FIELDS:
        filters |= Q(**{f"{field}__icontains": term})
    filters |= Q(brand__name__icontains=term)
    filters |= Q(category__name__icontains=term)
    filters |= Q(barcodes__code__iexact=term)
    return queryset.filter(filters).distinct()


def _postgres_search(queryset: QuerySet, term: str) -> QuerySet:
    """Full-text ranking combined with trigram similarity on the name.

    Full text handles "pao integral" matching "Pão Integral"; trigram catches
    the misspellings full text will not ("integrall").
    """
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    from django.contrib.postgres.trigram import TrigramSimilarity

    # `portuguese` is the deployment's primary market; unaccenting is handled by
    # the dictionary, so "pao" finds "pão".
    vector = (
        SearchVector("name", weight="A", config="portuguese")
        + SearchVector("short_description", weight="B", config="portuguese")
        + SearchVector("brand__name", weight="B", config="portuguese")
        + SearchVector("category__name", weight="C", config="portuguese")
        + SearchVector("description", weight="D", config="portuguese")
    )
    query = SearchQuery(term, config="portuguese", search_type="websearch")

    return (
        queryset.annotate(
            text_rank=SearchRank(vector, query),
            name_similarity=TrigramSimilarity("name", term),
        )
        .annotate(search_score=Greatest("text_rank", "name_similarity", Value(0.0)))
        .filter(
            Q(text_rank__gt=0)
            | Q(name_similarity__gt=SIMILARITY_THRESHOLD)
            | Q(sku__iexact=term)
            | Q(barcodes__code__iexact=term)
        )
        .distinct()
    )


def search_products(queryset: QuerySet, term: str) -> QuerySet:
    """Filter ``queryset`` by a free-text term.

    An empty term returns the queryset untouched, so callers can pass user input
    straight through without branching.
    """
    term = normalise_term(term)
    if not term:
        return queryset
    if is_postgres():
        return _postgres_search(queryset, term)
    return _fallback_search(queryset, term)


def order_by_relevance(queryset: QuerySet) -> QuerySet:
    """Sort by search score when one exists, otherwise by merchandising rules."""
    if is_postgres() and "search_score" in queryset.query.annotations:
        return queryset.order_by("-search_score", "-is_featured", "name")
    return queryset.order_by("-is_featured", "name")


def search_suggestions(queryset: QuerySet, term: str, *, limit: int = 8) -> list[str]:
    """Autocomplete labels for the search box."""
    term = normalise_term(term)
    if len(term) < 2:
        return []
    return list(search_products(queryset, term).values_list("name", flat=True).distinct()[:limit])
