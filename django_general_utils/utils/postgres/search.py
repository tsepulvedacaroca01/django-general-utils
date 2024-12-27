import re
from django.contrib.postgres.search import (
    TrigramSimilarity, SearchVector, SearchQuery, SearchRank, TrigramWordSimilarity
)
from django.db.models import F, CharField, Value, FloatField, QuerySet, IntegerField, Case, When
from django.db.models.functions import Cast, Greatest, Coalesce
from typing import Tuple


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
            search_rank_weights=None,
            search_fields_bonus_rank_startswith=None,
            order_by='-order_rank',
            min_value_by_field=0.0,
            bonus_by_field=0.1
    ):
        """

        @param queryset: QuerySet
        @param search_fields_filter: Tipo de búsqueda (gte, lte, etc)
        @param search_fields_average: Valor de filtro para la búsqueda
        @param search_trigram_fields: Campos para la búsqueda de trigramas
        @param search_word_trigram_fields: Campos para la búsqueda de trigramas de palabras
        @param search_vector_fields:  Campos para la búsqueda de vectores
        @param search_icontains_fields: Campos para la búsqueda de icontains
        @param search_terms: String de búsqueda
        @param search_rank_weights: Peso para generar un mejor rank
        @param search_fields_bonus_rank_startswith: Campos para la búsqueda de istartswith para dar un bonus de prioridad
        @return:
        """
        search_terms = search_terms.strip()
        search_trigram_fields = list(search_trigram_fields or [])
        search_word_trigram_fields = list(search_word_trigram_fields or [])
        search_vector_fields = list(search_vector_fields or [])
        search_icontains_fields = list(search_icontains_fields or [])
        search_fields_bonus_rank_startswith = search_fields_bonus_rank_startswith or set(search_trigram_fields + search_word_trigram_fields + search_icontains_fields)
        search_rank_weights = search_rank_weights or [0.2, 0.4, 0.6, 1]

        queryset, similarities_fields = PostgresSearch.get_similarity_annotate(
            queryset,
            search_trigram_fields,
            search_terms
        )
        queryset, word_similarities_fields = PostgresSearch.get_word_similarity_annotate(
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
        queryset, icontains_fields = PostgresSearch.get_icontains_annotate(queryset, search_icontains_fields, search_terms)
        queryset, istartswith_fields = PostgresSearch.get_start_istartswith_annotate(queryset, search_fields_bonus_rank_startswith, search_terms)

        fields = [
            *similarities_fields,
            *word_similarities_fields,
            'rank',
            *icontains_fields,
            *istartswith_fields,
        ]

        if len(fields) == 0:
            return queryset

        # Calculo la suma de los campos que tienen valor mayor a 0
        # noinspection PyTypeChecker
        fields_to_sum = Cast(sum(
            [
                Case(
                    When(**{f'{_field}__gt': 0}, then=1),
                    default=0,
                    output_field=IntegerField()
                ) for _field in fields
            ]
        ), output_field=IntegerField())

        # noinspection PyTypeChecker
        bonus_to_sum = Cast(sum(
            [
                Case(
                    When(**{f'{_field}__gt': min_value_by_field}, then=bonus_by_field),
                    default=0,
                    output_field=FloatField()
                ) for _field in fields
            ]
        ), output_field=FloatField())

        search_rank = F(fields[0])
        order_rank = F(fields[0])

        # Es para agregar valor mínimo que debe tener el rank para que sea considerado
        if len(fields) > 1:
            search_rank = Greatest(
                *fields,
                output_field=FloatField()
            )

        if len(fields) > 1:
            # noinspection PyTypeChecker
            order_rank = Cast(sum([Coalesce(F(_field), Value(0)) for _field in (fields)]), output_field=FloatField()) / F('fields_to_sum')

        return (
            queryset
            .annotate(
                fields_to_sum=fields_to_sum,
                bonus_to_sum=bonus_to_sum,
            )
            .annotate(
                # Es para agregar valor mínimo que debe tener el rank para que sea considerado
                search_rank=search_rank,
                # Es para ordenar por el rank
                order_rank=order_rank + F('bonus_to_sum')
            )
            .filter(**{f'search_rank__{search_fields_filter}': search_fields_average})
            .order_by(order_by)
        )

    @staticmethod
    def get_similarity_annotate(queryset, search_fields: list, search: str) -> Tuple[QuerySet, list[str]]:
        similarities = {}

        for _field in search_fields:
            similarities[f'{_field}_similarity'] = TrigramSimilarity(Cast(F(_field), output_field=CharField()), search)

        return queryset.annotate(**similarities), list(similarities.keys())

    @staticmethod
    def get_word_similarity_annotate(queryset, search_fields: list, search: str) -> Tuple[QuerySet, list[str]]:
        word_similarities = {}

        for _search_field in search_fields:
            for _search in search.split(' '):
                _search_key = re.sub(r'[^\w\s]', '', _search).strip()

                if not _search or not _search_key:
                    continue

                word_similarities[f'{_search_field}_word_similarity_{_search_key}'] = Coalesce(
                    TrigramWordSimilarity(
                        _search,
                        Cast(F(_search_field), output_field=CharField())
                    ),
                    0.0
                )

        return queryset.annotate(**word_similarities), list(word_similarities.keys())

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
    def get_icontains_annotate(queryset, search_fields: list, search: str, add_rank_value: int = 0.5) -> Tuple[QuerySet, list[str]]:
        """
        AGREGO PUNTOS PARA BUSCAR LOS CAMPOS QUE CONTIENEN EL TEXTO
        """
        whens = []

        for _value in search.lower().split(' '):
            for _field in search_fields:
                if not _value:
                    continue

                whens.append(
                    When(**{f'{_field}__icontains': _value, 'then': add_rank_value})
                )

        if len(whens) == 0:
            return queryset, []

        icontains_rank = Case(
            *whens,
            default=0,
            output_field=IntegerField()
        )

        return queryset.annotate(icontains_rank=icontains_rank), ['icontains_rank']

    @staticmethod
    def get_start_istartswith_annotate(queryset, search_fields: list, search: str, bonus_rank_startswith: float = 1.5 ) -> Tuple[QuerySet, list[str]]:
        """
        AGREGO PUNTOS PARA BUSCAR LOS CAMPOS QUE COMIENZAN CON EL IGUALANDO EL FORMATO
        """
        whens = []

        for _field in search_fields:
            if not search or bonus_rank_startswith == 0:
                break

            whens.append(
                When(**{f'{_field}__istartswith': search, 'then': bonus_rank_startswith})
            )

        if len(whens) == 0:
            return queryset, []

        istartswith = Case(
            *whens,
            default=0,
            output_field=IntegerField()
        )

        return queryset.annotate(istartswith_rank=istartswith), ['istartswith_rank']
