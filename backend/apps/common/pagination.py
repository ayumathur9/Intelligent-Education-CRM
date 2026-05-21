"""
Pagination classes — LOW-002.

StandardResultsSetPagination: page-number pagination (default for most endpoints).
CursorResultsSetPagination: cursor-based pagination for large datasets (students list).
  - Immune to page-drift when records are inserted/deleted mid-pagination.
  - Opaque cursor prevents enumeration attacks.
  - Only supports forward iteration (no random page access).
"""
from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class CursorResultsSetPagination(CursorPagination):
    """
    Cursor pagination for the students list endpoint.

    Usage: add ``?cursor=<opaque_token>`` from the ``next`` link in responses.
    Ordering is always by ``-created_at`` then ``pk`` (stable deterministic order).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = ("-created_at", "pk")
