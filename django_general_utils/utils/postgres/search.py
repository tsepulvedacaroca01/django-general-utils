from django.contrib.postgres.search import (
    TrigramSimilarity, SearchVector, SearchQuery, SearchRank, TrigramWordSimilarity
)
from django.db.models import F, CharField, Value, FloatField, Q, QuerySet
from django.db.models.functions import Cast, Greatest


class PostgresSearch:
    @staticmethod
    def get_queryset(
            queryset,
            search_fields_filter='gte',
            search_fields_average=0.35,
            search_trigram_fields=None,
            search_word_trigram_fields=None,
            search_vector_fields=None,
            search_icontains_fields=None,
            search_terms='',
            search_rank_weights=None
    ):
        search_trigram_fields = search_trigram_fields or []
        search_word_trigram_fields = search_word_trigram_fields or []
        search_vector_fields = search_vector_fields or []
        search_icontains_fields = search_icontains_fields or []
        search_rank_weights = search_rank_weights or [0.2, 0.4, 0.6, 1]

        queryset = PostgresSearch.get_similarity_annotate(
            queryset,
            search_trigram_fields,
            search_terms
        )
        queryset = PostgresSearch.get_word_similarity_annotate(
            queryset,
            search_word_trigram_fields,
            search_terms
        )
        queryset = PostgresSearch.get_vector_annotate(
            queryset,
            search_vector_fields,
            search_terms,
            search_rank_weights
        )

        q = PostgresSearch.get_icontains(search_icontains_fields, search_terms)
        q |= Q(**{f'search_rank__{search_fields_filter}': search_fields_average})

        return queryset \
            .annotate(search_rank=Greatest('similarity', 'word_similarity', 'rank')) \
            .filter(q) \
            .order_by('-search_rank')

    @staticmethod
    def get_similarity(search_fields: list, search: str) -> TrigramSimilarity:
        trigram = TrigramSimilarity(Cast(F(search_fields[0]), output_field=CharField()), search)

        for _field in search_fields[1:]:
            trigram += TrigramSimilarity(Cast(F(_field), output_field=CharField()), search)

        return trigram

    @staticmethod
    def get_similarity_annotate(queryset, search_fields: list, search: str) -> QuerySet:
        similarity = Value(0, output_field=FloatField())

        if len(search_fields) != 0:
            similarity = PostgresSearch.get_similarity(search_fields, search)

        return queryset.annotate(similarity=similarity)

    @staticmethod
    def get_word_similarity(search_fields: list, search: str) -> list[TrigramWordSimilarity]:
        word_trigrams = [
            TrigramWordSimilarity(search, Cast(F(search_fields[0]), output_field=CharField()))
        ]

        for _field in search_fields[1:]:
            word_trigrams.append(
                TrigramWordSimilarity(search, Cast(F(_field), output_field=CharField()))
            )

        return word_trigrams

    @staticmethod
    def get_word_similarity_annotate(queryset, search_fields: list, search: str) -> QuerySet:
        words_similarity = [Value(0, output_field=FloatField())]

        if len(search_fields) != 0:
            for _search in search.split(' '):
                words_similarity += PostgresSearch.get_word_similarity(search_fields, _search)

        return queryset.annotate(
            word_similarity=words_similarity[0] if len(words_similarity) == 1 else Greatest(*words_similarity)
        )

    @staticmethod
    def get_vector(
            search_fields: list[dict],
            search: str,
            vector_language='spanish',
            weights=None,
    ) -> SearchRank:
        weights = weights or [0.2, 0.4, 0.6, 1]
        first_field = search_fields[0]

        vector = SearchVector(
            first_field['field'],
            weight=first_field.get('weight', 'A'),
            config=first_field.get('config', vector_language),
        )

        for _field in search_fields[1:]:
            vector += SearchVector(
                _field['field'],
                weight=_field.get('weight', 'A'),
                config=_field.get('config', vector_language),
            )

        search_query = SearchQuery(
            search, config=vector_language
        )

        return SearchRank(
            vector,
            search_query,
            weights=weights,
        )

    @staticmethod
    def get_vector_annotate(queryset, search_fields: list, search: str, weights=None) -> QuerySet:
        weights = weights or [0.2, 0.4, 0.6, 1]
        rank = Value(0, output_field=FloatField())

        if len(search_fields) != 0:
            rank = PostgresSearch.get_vector(search_fields, search, weights=weights)

        return queryset.annotate(rank=rank)

    @staticmethod
    def get_icontains(search_fields: list, search: str) -> Q:
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
