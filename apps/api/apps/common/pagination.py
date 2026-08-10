"""Pagination defaults.

Every list endpoint is paginated: an unbounded list endpoint is a denial of
service waiting to happen once a tenant has a real catalog.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    """Page-number pagination with a hard ceiling on ``page_size``."""

    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("pages", self.page.paginator.num_pages),
                    ("page_size", self.get_page_size(self.request)),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


class LargePagination(DefaultPagination):
    """For admin tables that legitimately show more rows at once."""

    page_size = 50
    max_page_size = 200


class TimelinePagination(CursorPagination):
    """Stable pagination for append-only feeds (audit log, order history).

    Cursor pagination avoids the skipped/duplicated rows that page numbers
    produce when new records arrive while a user is paging.
    """

    page_size = 50
    max_page_size = 200
    page_size_query_param = "page_size"
    ordering = "-created_at"
