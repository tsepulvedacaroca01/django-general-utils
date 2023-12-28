from django.db.models import Q
from nested_multipart_parser import NestedParser
from rest_framework import filters

from ....utils import str_to_boolean


class OrFilter(filters.BaseFilterBackend):
    search_attribute = 'filter_or_fields'
    search_param_key = 'or'

    def filter_queryset(self, request, queryset, view):
        search_fields = self.get_search_fields(view)
        search_terms = self.get_query_params(request)

        if not search_fields or not search_terms:
            return queryset

        queryset = queryset.filter(
            self.get_filter(search_fields, search_terms)
        )

        return queryset.distinct()

    def get_search_fields(self, view) -> list:
        """
        Search fields are obtained from the view, but the request is always
        """
        return getattr(view, self.search_attribute, None)

    def get_query_params(self, request) -> dict:
        """
        Gey query params and formatted to dict
        """
        parser = NestedParser(request.query_params, {'querydict': False})

        if not parser.is_valid():
            return {}

        return parser.validate_data.get(self.search_param_key, {})

    def get_filter(self, search_fields: list, search_terms: dict) -> Q:
        """
        set filter query
        """
        q = Q()

        for _key, _value in search_terms.items():
            if _value == '' or _key not in search_fields:
                continue

            q |= Q(**{_key: str_to_boolean(_value, True)})

        return q
