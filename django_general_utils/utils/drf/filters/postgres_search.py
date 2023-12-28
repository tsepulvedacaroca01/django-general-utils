from django.contrib.postgres.search import (
    TrigramSimilarity, SearchVector, SearchQuery, SearchRank, TrigramWordSimilarity
)
from django.db.models import F, CharField, Value, FloatField, Q, QuerySet
from django.db.models.functions import Cast, Greatest
from nested_multipart_parser import NestedParser
from rest_framework import filters
from rest_framework.settings import api_settings


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
    search_rank_weights_attribute = 'search_rank_weights'

    def filter_queryset(self, request, queryset, view):
        search_terms = self.get_search_terms(request, view)
        search_trigram_fields = self.get_search_trigram_fields(view)
        search_word_trigram_fields = self.get_search_word_trigram_fields(view)
        search_vector_fields = self.get_search_vector_fields(view)
        search_icontains_fields = self.get_search_icontains_fields(view)

        if search_terms is None or search_terms == '':
            return queryset

        search_fields_filter = self.get_search_fields_filter(view)
        search_fields_average = self.get_search_fields_average(view)
        queryset = self.get_similarity_annotate(queryset, search_trigram_fields, search_terms)
        queryset = self.get_word_similarity_annotate(queryset, search_word_trigram_fields, search_terms)
        queryset = self.get_vector_annotate(view, queryset, search_vector_fields, search_terms)

        q = self.get_icontains(search_icontains_fields, search_terms)
        q |= Q(**{f'search_rank__{search_fields_filter}': search_fields_average})

        return queryset \
            .annotate(search_rank=Greatest('similarity', 'word_similarity', 'rank')) \
            .filter(q) \
            .order_by('-search_rank')

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

    def get_vector_language(self, view) -> list:
        return getattr(view, self.vector_language_attribute, 'spanish')

    def get_search_fields_filter(self, view) -> list:
        return getattr(view, self.search_fields_filter_attribute, 'gte')

    def get_search_fields_average(self, view) -> list:
        return getattr(view, self.search_fields_average_attribute, 0.35)

    def get_similarity(self, search_fields: list, search: str) -> TrigramSimilarity:
        trigram = TrigramSimilarity(Cast(F(search_fields[0]), output_field=CharField()), search)

        for _field in search_fields[1:]:
            trigram += TrigramSimilarity(Cast(F(_field), output_field=CharField()), search)

        return trigram

    def get_similarity_annotate(self, queryset, search_fields: list, search: str) -> QuerySet:
        similarity = Value(0, output_field=FloatField())

        if len(search_fields) != 0:
            similarity = self.get_similarity(search_fields, search)

        return queryset.annotate(similarity=similarity)

    def get_word_similarity(self, search_fields: list, search: str) -> list[TrigramWordSimilarity]:
        word_trigrams = [
            TrigramWordSimilarity(search, Cast(F(search_fields[0]), output_field=CharField()))
        ]

        for _field in search_fields[1:]:
            word_trigrams.append(
                TrigramWordSimilarity(search, Cast(F(_field), output_field=CharField()))
            )

        return word_trigrams

    def get_word_similarity_annotate(self, queryset, search_fields: list, search: str) -> QuerySet:
        words_similarity = [Value(0, output_field=FloatField())]

        if len(search_fields) != 0:
            for _search in search.split(' '):
                words_similarity += self.get_word_similarity(search_fields, _search)

        return queryset.annotate(
            word_similarity=words_similarity[0] if len(words_similarity) == 1 else Greatest(*words_similarity)
        )

    def get_vector(self, search_fields: list[dict], search: str, view) -> SearchRank:
        first_field = search_fields[0]

        vector = SearchVector(
            first_field['field'],
            weight=first_field.get('weight', 'A'),
            config=first_field.get('config', self.get_vector_language(view)),
        )

        for _field in search_fields[1:]:
            vector += SearchVector(
                _field['field'],
                weight=_field.get('weight', 'A'),
                config=_field.get('config', self.get_vector_language(view)),
            )

        search_query = SearchQuery(
            search, config=self.get_vector_language(view)
        )

        return SearchRank(
            vector,
            search_query,
            weights=getattr(view, self.search_rank_weights_attribute, [0.2, 0.4, 0.6, 1])
        )

    def get_vector_annotate(self, view, queryset, search_fields: list, search: str) -> QuerySet:
        rank = Value(0, output_field=FloatField())

        if len(search_fields) != 0:
            rank = self.get_vector(search_fields, search, view)

        return queryset.annotate(rank=rank)

    def get_icontains(self, search_fields: list, search: str) -> Q:
        """
        set filter query
        """
        q = Q()

        for _value in search.lower().split(' '):
            for _field in search_fields:
                if not _value:
                    continue

                q |= Q(**{f'{_field}__icontains': _value})

        return q
