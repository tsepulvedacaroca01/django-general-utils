from nested_multipart_parser import NestedParser
from rest_framework import filters
from rest_framework.settings import api_settings

from ....utils.postgres.search import PostgresSearch


class PostgresSearchFilter(filters.BaseFilterBackend):
    """
    Filter with Trigrams, Vector and contains.
    """
    search_param_attribute = 'search_param'
    search_fields_average_attribute = 'search_fields_average' # 0.5, 0.25, etc
    search_fields_filter_attribute = 'search_fields_filter' # gte, lte, etc
    vector_language_attribute = 'vector_language' # spanish, english, etc

    search_trigram_attribute = 'search_trigram_fields'
    search_word_trigram_attribute = 'search_word_trigram_fields'
    search_vector_attribute = 'search_vector_fields'
    search_icontains_attribute = 'search_icontains_fields'
    search_bonus_rank_startswith = 'search_fields_bonus_rank_startswith'
    search_rank_weights_attribute = 'search_rank_weights'

    def filter_queryset(self, request, queryset, view):
        search_terms = self.get_search_terms(request, view)
        search_trigram_fields = self.get_search_trigram_fields(view)
        search_word_trigram_fields = self.get_search_word_trigram_fields(view)
        search_vector_fields = self.get_search_vector_fields(view)
        search_icontains_fields = self.get_search_icontains_fields(view)
        search_fields_bonus_rank_startswith = self.get_search_fields_bonus_rank_startswith(view)

        if search_terms is None or search_terms == '':
            return queryset

        search_fields_filter = self.get_search_fields_filter(view)
        search_fields_average = self.get_search_fields_average(view)
        search_rank_weights = getattr(view, self.search_rank_weights_attribute, [0.2, 0.4, 0.6, 1])

        return PostgresSearch.get_queryset(
            queryset,
            search_fields_filter,
            search_fields_average,
            search_trigram_fields,
            search_word_trigram_fields,
            search_vector_fields,
            search_icontains_fields,
            search_terms,
            search_rank_weights,
            search_fields_bonus_rank_startswith=search_fields_bonus_rank_startswith
        )

    def get_search_param(self, view) -> str:
        return getattr(view, self.search_param_attribute, api_settings.SEARCH_PARAM)

    def get_search_terms(self, request, view) -> str | None:
        parser = NestedParser(request.query_params, {'querydict': False})

        if not parser.is_valid():
            return None

        return parser.validate_data.get(self.get_search_param(view), None)

    def get_search_trigram_fields(self, view) -> list:
        return getattr(view, self.search_trigram_attribute, [])

    def get_search_word_trigram_fields(self, view) -> list:
        return getattr(view, self.search_word_trigram_attribute, [])

    def get_search_vector_fields(self, view) -> list:
        return getattr(view, self.search_vector_attribute, [])

    def get_search_icontains_fields(self, view) -> list:
        return getattr(view, self.search_icontains_attribute, [])

    def get_search_fields_bonus_rank_startswith(self, view) -> list:
        return getattr(view, self.search_bonus_rank_startswith, [])

    def get_vector_language(self, view) -> list:
        return getattr(view, self.vector_language_attribute, 'spanish')

    def get_search_fields_filter(self, view) -> str:
        return getattr(view, self.search_fields_filter_attribute, 'gte')

    def get_search_fields_average(self, view) -> float:
        return getattr(view, self.search_fields_average_attribute, 0.35)
