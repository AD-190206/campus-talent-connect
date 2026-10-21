from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ContractPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        for name, default, maximum in (
            ("page", 1, None),
            ("page_size", self.page_size, self.max_page_size),
        ):
            raw_value = request.query_params.get(name)

            if raw_value is None:
                continue

            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                raise ValidationError({
                    name: "Must be a positive integer."
                })

            if value < 1 or (maximum is not None and value > maximum):
                raise ValidationError({
                    name: (
                        f"Must be between 1 and {maximum}."
                        if maximum is not None
                        else "Must be a positive integer."
                    )
                })

        self.request = request
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return Response({
            "data": data,
            "message": "Records retrieved successfully.",
            "pagination": {
                "page": self.page.number,
                "page_size": self.page.paginator.per_page,
                "total": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
            },
        })
