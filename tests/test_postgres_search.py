import os
import unittest

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        BASE_DIR=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'django_general_utils')),
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=(
            'django.contrib.auth',
            'django.contrib.contenttypes',
        ),
        TIME_ZONE='UTC',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.AutoField',
    )
    django.setup()

from django.db import models

from django_general_utils.utils.postgres.search import PostgresSearch
from django_general_utils.utils.postgres.search_v2 import PostgresSearchV2


class WordSimilarityAnnotateModel(models.Model):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_postgres_search_word_similarity_model'


# get_word_similarity_annotate() only builds the annotate() expression tree — it never executes
# SQL, so the alias validation (Query.check_alias, triggered inside .annotate()) can be exercised
# against sqlite without a real Postgres backend.
class GetWordSimilarityAnnotateTests(unittest.TestCase):
    def test_tab_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearch.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\tdef'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None

    def test_non_breaking_space_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearch.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\xa0def'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None

    def test_newline_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearch.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\ndef'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None

    def test_v2_tab_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearchV2.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\tdef'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None

    def test_v2_non_breaking_space_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearchV2.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\xa0def'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None

    def test_v2_newline_in_search_term_does_not_raise_and_sanitizes_alias(self) -> None:
        queryset, aliases = PostgresSearchV2.get_word_similarity_annotate(
            WordSimilarityAnnotateModel.objects.all(), ['name'], 'abc\ndef'
        )
        self.assertEqual(aliases, ['name_word_similarity_abc', 'name_word_similarity_def'])

        return None
