"""
Pagination for the Courses app.

Standard page-number pagination with a configurable page size.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CoursePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: list) -> Response:
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "example": 42},
                "next": {"type": "string", "nullable": True, "example": "http://api/courses/?page=2"},
                "previous": {"type": "string", "nullable": True, "example": None},
                "results": schema,
            },
            "required": ["count", "next", "previous", "results"],
        }
