import re
from typing import Tuple

from django.contrib.postgres.search import (
    TrigramSimilarity, SearchRank, TrigramWordSimilarity, SearchQuery
)
from django.db.models import F, CharField, FloatField, QuerySet, Q
from django.db.models.functions import Cast, Greatest, Coalesce


class PostgresSearchV2:
    @staticmethod
    def get_queryset(
            queryset: QuerySet,
            search_terms='',
            search_fields_filter='gte',
            search_fields_average=0.30,
            search_trigram_fields=None,
            search_word_trigram_fields=None,
            search_vector_field=None,
            search_rank_weights=None,
            order_by='-order_rank',
    ) -> QuerySet:
        """
        Aplica búsqueda Full-Text y de Trigramas de forma optimizada.
        Filtra primero mediante índices GIN y luego calcula el ranking.
        """
        search_terms = search_terms.strip()

        if not search_terms:
            return queryset

        search_trigram_fields = list(search_trigram_fields or [])
        search_word_trigram_fields = list(search_word_trigram_fields or [])
        search_rank_weights = search_rank_weights or [0.2, 0.4, 0.6, 1.0]

        # =========================================================
        # PASO 1: CONSTRUIR EL FILTRO ESCUDO (Usa los índices GIN)
        # =========================================================
        base_filter = Q()
        search_query = None
        optimized_rank_expression = None

        # A. Si hay vector, preparamos la query y agregamos al filtro OR
        if search_vector_field:
            search_query, optimized_rank_expression = PostgresSearchV2.get_optimized_vector(
                search_vector_field,
                search_terms,
                weights=search_rank_weights
            )
            base_filter |= Q(**{search_vector_field: search_query})

        # B. Trigramas normales (para palabras completas con errores, ej: "dezarrllador")
        for field in search_trigram_fields:
            base_filter |= Q(**{f'{field}__trigram_similar': search_terms})

        # C. Trigramas de palabra (IDEAL para cuando escriben fragmentos como "desarrol")
        for field in search_word_trigram_fields:
            base_filter |= Q(**{f'{field}__trigram_word_similar': search_terms})

        # D. EL SALVAVIDAS: Búsquedas cortas (autocompletado)
        # Si el usuario escribió 3 letras o menos, la matemática de trigramas
        # suele fallar (umbral < 0.3). Usamos icontains SOLO en el filtro inicial
        # para dejar pasar estas filas y que se evalúen en los siguientes pasos.
        if len(search_terms) <= 3:
            for field in set(search_word_trigram_fields + search_trigram_fields):
                base_filter |= Q(**{f'{field}__icontains': search_terms})

        # =========================================================
        # PASO 2: FILTRAR LA BASE DE DATOS RÁPIDAMENTE
        # =========================================================
        # Esto reduce drásticamente las filas a evaluar en milisegundos.
        if base_filter:
            queryset = queryset.filter(base_filter)

        # =========================================================
        # PASO 3: AHORA SÍ, HACEMOS TODA LA MATEMÁTICA PESADA
        # =========================================================
        # Estas anotaciones ahora solo correrán para las filas filtradas
        queryset, similarities_fields = PostgresSearchV2.get_similarity_annotate(
            queryset,
            search_trigram_fields,
            search_terms
        )
        queryset, word_similarities_fields = PostgresSearchV2.get_word_similarity_annotate(
            queryset,
            search_word_trigram_fields,
            search_terms
        )

        # Anotamos el vector optimizado
        if search_vector_field and optimized_rank_expression is not None:
            queryset = queryset.annotate(optimized_rank=optimized_rank_expression)

        # =========================================================
        # PASO 4: CÁLCULO FINAL DE ORDENAMIENTO
        # =========================================================
        fields = [
            *similarities_fields,
            *word_similarities_fields,
        ]

        if search_vector_field:
            fields.append('optimized_rank')

        if not fields:
            return queryset

        # 1. Protegemos contra nulos convirtiendo todo a FloatField
        coalesced_fields = [
            Coalesce(F(_field), 0.0, output_field=FloatField())
            for _field in fields
        ]

        # 2. search_rank: El mejor puntaje individual (ideal para filtrar la calidad final)
        search_rank = Greatest(*coalesced_fields, output_field=FloatField())

        # 3. order_rank: La suma de todos los puntajes (ideal para priorizar)
        order_rank = sum(coalesced_fields)

        return (
            queryset
            .annotate(
                search_rank=search_rank,
                order_rank=order_rank
            )
            # Filtramos dinámicamente según el threshold (ej. >= 0.35)
            .filter(**{f'search_rank__{search_fields_filter}': search_fields_average})
            # Ordenamos por la suma total, de mayor a menor
            .order_by(order_by)
        )

    @staticmethod
    def get_similarity_annotate(queryset: QuerySet, search_fields: list, search: str) -> Tuple[QuerySet, list[str]]:
        similarities = {}

        for _field in search_fields:
            similarities[f'{_field}_similarity'] = TrigramSimilarity(Cast(F(_field), output_field=CharField()), search)

        return queryset.annotate(**similarities), list(similarities.keys())

    @staticmethod
    def get_word_similarity_annotate(queryset: QuerySet, search_fields: list, search: str) -> Tuple[QuerySet, list[str]]:
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
    def get_optimized_vector(
            vector_field_name: str,
            search_string: str,
            vector_language='spanish',
            weights=None,
    ) -> Tuple[SearchQuery, SearchRank]:
        """
        Retorna el SearchQuery (para el filtro) y el SearchRank (para la anotación).
        """
        weights = weights or [0.2, 0.4, 0.6, 1.0]

        search_query = SearchQuery(search_string, config=vector_language)
        search_rank = SearchRank(F(vector_field_name), search_query, weights=weights)

        return search_query, search_rank
