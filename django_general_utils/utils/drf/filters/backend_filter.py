from nested_multipart_parser import NestedParser
from rest_framework import filters

from ....utils import str_to_boolean


class BackendFilter(filters.BaseFilterBackend):
    filter_fields_attribute = 'filter_fields'
    filter_exclude_fields_attribute = 'filter_exclude_fields'

    def filter_queryset(self, request, queryset, view):
        filter_fields = self.get_filter_fields(view)
        exclude_filter_fields = self.get_filter_exclude_fields(view)
        search_terms = self.get_query_params(request)

        if not search_terms:
            return queryset

        if len(filter_fields) == 0 and len(exclude_filter_fields) == 0:
            return queryset

        queryset = queryset.filter(
            **self.get_filter(filter_fields, search_terms)
        ).exclude(
            **self.get_exclude_fields(exclude_filter_fields, search_terms)
        )

        return queryset

    def get_filter_fields(self, view) -> list:
        return getattr(view, self.filter_fields_attribute, [])

    def get_filter_exclude_fields(self, view) -> list:
        return getattr(view, self.filter_exclude_fields_attribute, [])

    def get_query_params(self, request) -> dict:
        parser = NestedParser(request.query_params, {'querydict': False})

        if not parser.is_valid():
            return {}

        return parser.validate_data

    def get_filter(self, search_fields: list, search_terms: dict) -> dict:
        dynamic_filter = {}

        for _key, _value in search_terms.items():
            if _key not in search_fields:
                continue

            dynamic_filter[_key] = str_to_boolean(_value, True)

        return dynamic_filter

    def get_exclude_fields(self, exclude_fields: list, search_terms: dict) -> dict:
        dynamic_filter = {}

        for _key, _value in search_terms.items():
            if _key not in exclude_fields or '!' not in _key:
                continue

            dynamic_filter[_key.replace('!', '')] = str_to_boolean(_value, True)

        return dynamic_filter
