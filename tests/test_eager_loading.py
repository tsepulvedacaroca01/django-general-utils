import unittest

import django
from django.conf import settings

if not settings.configured:
    import os

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

from django.core.management import call_command
from django.db import connection, models
from django.db.models import Count, Value
from django.db.models.functions import Concat
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from queryable_properties.properties import queryable_property
from rest_framework import serializers

from django_general_utils.models import BaseV3
from django_general_utils.utils.drf.eager_loading import (
    AutoEagerLoadingAjaxDatatableMixin,
    AutoEagerLoadingMixin,
    build_eager_queryset,
    eager_relations_from_column_defs,
)
from django_general_utils.utils.drf.fields import LazyRefSerializerField, NestedPrimaryKeyRelatedField
from django_general_utils.utils.rest_ql import DynamicFieldsMixin

# ---------------------------------------------------------------------------
# Models — a small graph big enough to exercise every real case found while
# migrating this from a consuming project: forward FK, reverse FK (many),
# a queryable_property on the root model, a queryable_property on a related
# model (forces Prefetch instead of select_related), a 2-level forward chain,
# and a plain field with a dotted `source=` pointing into an undeclared FK.
# ---------------------------------------------------------------------------

class Country(BaseV3):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_country'


class Author(BaseV3):
    name = models.CharField(max_length=64, null=True, blank=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.CASCADE, related_name='authors')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_author'

    # noinspection PyTypeChecker
    @queryable_property(annotation_based=True)
    @classmethod
    def label(cls):
        return Concat('name', Value(' (author)'), output_field=models.CharField())


class Book(BaseV3):
    title = models.CharField(max_length=64, null=True, blank=True)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='books')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_book'

    # noinspection PyTypeChecker
    @queryable_property(annotation_based=True)
    @classmethod
    def chapters_count(cls):
        return Count('chapters', distinct=True)


class Chapter(BaseV3):
    title = models.CharField(max_length=64, null=True, blank=True)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='chapters')
    editor = models.ForeignKey(Author, null=True, blank=True, on_delete=models.CASCADE, related_name='+')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_chapter'


class Review(BaseV3):
    comment = models.CharField(max_length=64, null=True, blank=True)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reviews')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_review'


class Warehouse(BaseV3):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_warehouse'


class Location(BaseV3):
    code = models.CharField(max_length=64, null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='locations')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_location'


_MODELS = (Country, Author, Book, Chapter, Review, Warehouse, Location)


# ---------------------------------------------------------------------------
# Serializers — each isolates one concern; see the class docstrings below for
# which scenario they exist to cover.
# ---------------------------------------------------------------------------

class CountrySerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('pk', 'name')


class AuthorLiteSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """No `label` in `Meta.fields` -- embedding this never needs a queryable_property."""

    class Meta:
        model = Author
        fields = ('pk', 'name')


class AuthorWithLabelSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """`label` is a queryable_property, not a declared field -- embedding this forces Prefetch."""

    class Meta:
        model = Author
        fields = ('pk', 'name', 'label')


class AuthorWithCountrySerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """Forward FK nested inside another forward FK -- exercises a 2-level select_related chain."""

    country = LazyRefSerializerField(serializer_class=CountrySerializer, extra_kwargs={'fields': ['pk', 'name']})

    class Meta:
        model = Author
        fields = ('pk', 'name', 'country')


class ReviewSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ('pk', 'comment')


class ChapterSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    editor = NestedPrimaryKeyRelatedField(
        queryset=Author.objects.all(),
        serializer_class=AuthorLiteSerializer,
        extra_kwargs={'fields': ['pk', 'name']},
    )

    class Meta:
        model = Chapter
        fields = ('pk', 'title', 'editor')


class BookSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """
    The 'everything' serializer: a forward FK whose nested serializer needs a
    queryable_property (`author` -> Prefetch), a `many=True` LazyRefSerializerField
    whose nested serializer has its own forward FK (`chapters` -> Prefetch with a
    nested select_related), a `many=True` NestedPrimaryKeyRelatedField (`reviews`),
    and a queryable_property on the root model itself (`chapters_count`).
    """

    author = LazyRefSerializerField(
        serializer_class=AuthorWithLabelSerializer,
        extra_kwargs={'fields': ['pk', 'name', 'label']},
    )
    chapters = LazyRefSerializerField(serializer_class=ChapterSerializer, many=True)
    reviews = NestedPrimaryKeyRelatedField(
        queryset=Review.objects.all(), serializer_class=ReviewSerializer, many=True,
    )

    class Meta:
        model = Book
        fields = ('pk', 'title', 'author', 'chapters', 'reviews', 'chapters_count')


class BookAuthorWithoutLabelSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """`extra_kwargs` excludes `label` -- `author` should stay a plain select_related."""

    author = LazyRefSerializerField(
        serializer_class=AuthorWithLabelSerializer,
        extra_kwargs={'fields': ['pk', 'name']},
    )

    class Meta:
        model = Book
        fields = ('pk', 'title', 'author')


class BookWithAuthorCountrySerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    author = LazyRefSerializerField(
        serializer_class=AuthorWithCountrySerializer,
        extra_kwargs={'fields': ['pk', 'name', 'country']},
    )

    class Meta:
        model = Book
        fields = ('pk', 'title', 'author')


class BookCountOnlySerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """No relation fields at all -- isolates the root queryable_property with
    zero interference from any Prefetch that `.get()` would otherwise also
    evaluate."""

    class Meta:
        model = Book
        fields = ('pk', 'title', 'chapters_count')


class BookAuthorAndCountSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """
    Narrower than `BookSerializer` on purpose: no `chapters`/`reviews`, so
    query-count assertions only measure what `author` (with its
    queryable_property) and the root `chapters_count` actually cost --
    `.get()` on a queryset with any `prefetch_related()` fetches every
    declared prefetch, not just the one under test.
    """

    author = LazyRefSerializerField(
        serializer_class=AuthorWithLabelSerializer,
        extra_kwargs={'fields': ['pk', 'name', 'label']},
    )

    class Meta:
        model = Book
        fields = ('pk', 'title', 'author', 'chapters_count')


class LocationSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """`warehouse` is never declared as its own field -- only reachable via `source=`."""

    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = Location
        fields = ('pk', 'code', 'warehouse_name')


class _SchemaBackedTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)

        with connection.schema_editor() as schema_editor:
            for model in _MODELS:
                schema_editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            for model in reversed(_MODELS):
                schema_editor.delete_model(model)

        super().tearDownClass()

    def setUp(self):
        for model in reversed(_MODELS):
            model.objects.all().delete()


class BuildEagerQuerysetTests(_SchemaBackedTestCase):
    def test_forward_fk_uses_select_related(self):
        qs = build_eager_queryset(Book.objects.all(), BookAuthorWithoutLabelSerializer)

        self.assertEqual(qs.query.select_related, {'author': {}})
        self.assertEqual(qs._prefetch_related_lookups, ())

    def test_reverse_fk_and_many_relations_use_prefetch_related(self):
        qs = build_eager_queryset(Book.objects.all(), BookSerializer)

        lookups = {p.prefetch_through for p in qs._prefetch_related_lookups}
        self.assertEqual(lookups, {'author', 'chapters', 'reviews'})

    def test_many_true_lazy_ref_serializer_field_resolves_nested_serializer(self):
        # Regression test: `many_init` (fields/lazy_ref_field.py) resolves
        # `.child` eagerly to a built serializer *instance*, not the lazy
        # field -- if `_resolve_nested_serializer_class` used
        # `get_serializer_class()` on it directly, this silently returns
        # nothing and the `chapters` prefetch queryset stays fully unoptimized.
        qs = build_eager_queryset(Book.objects.all(), BookSerializer)
        chapters_prefetch = next(p for p in qs._prefetch_related_lookups if p.prefetch_through == 'chapters')

        self.assertEqual(chapters_prefetch.queryset.query.select_related, {'editor': {}})

    def test_many_true_nested_primary_key_related_field_resolves_nested_serializer(self):
        # Same regression as above, for the ManyRelatedField-wrapping path.
        qs = build_eager_queryset(Book.objects.all(), BookSerializer)
        reviews_prefetch = next(p for p in qs._prefetch_related_lookups if p.prefetch_through == 'reviews')

        # ReviewSerializer has no relations of its own -- reaching this point
        # without an exception is what matters (nested_serializer_class resolved).
        self.assertEqual(reviews_prefetch.queryset.model, Review)

    def test_root_queryable_property_uses_select_properties(self):
        author = Author.objects.create(name='Jane')
        book = Book.objects.create(title='A Book', author=author)

        qs = build_eager_queryset(Book.objects.all(), BookCountOnlySerializer)

        with CaptureQueriesContext(connection) as ctx:
            fetched = qs.get(pk=book.pk)
            _ = fetched.chapters_count

        self.assertEqual(fetched.chapters_count, 0)
        # `select_properties('chapters_count')` should have annotated the value
        # onto the row already fetched -- accessing it afterwards costs 0 queries.
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_related_model_queryable_property_forces_prefetch_not_select_related(self):
        # `select_properties()` raises "Cannot select properties on related
        # models." for a dotted path -- a queryable_property needed by a
        # nested serializer can only be resolved via Prefetch (a separate
        # query with its own select_properties), never a select_related JOIN.
        qs = build_eager_queryset(Book.objects.all(), BookSerializer)

        self.assertNotIn('author', qs.query.select_related or {})
        lookups = {p.prefetch_through for p in qs._prefetch_related_lookups}
        self.assertIn('author', lookups)

    def test_related_model_queryable_property_resolves_with_zero_extra_queries(self):
        author = Author.objects.create(name='Jane')
        book = Book.objects.create(title='A Book', author=author)

        qs = build_eager_queryset(Book.objects.all(), BookAuthorAndCountSerializer)

        with CaptureQueriesContext(connection) as ctx:
            fetched = qs.get(pk=book.pk)
            label = fetched.author.label

        self.assertEqual(label, 'Jane (author)')
        # 1 query for Book (+ chapters_count annotation), 1 batched Prefetch
        # query for `author` (with `label` already annotated on it).
        self.assertEqual(len(ctx.captured_queries), 2)

    def test_extra_kwargs_ceiling_excludes_unrequested_queryable_property(self):
        # AuthorWithLabelSerializer *can* render `label`, but this particular
        # embedding restricts it out via extra_kwargs -- own_props should come
        # back empty and `author` should stay select_related, not Prefetch.
        qs = build_eager_queryset(Book.objects.all(), BookAuthorWithoutLabelSerializer)

        self.assertIn('author', qs.query.select_related)
        self.assertEqual(qs._prefetch_related_lookups, ())

    def test_two_level_forward_chain_via_select_related(self):
        qs = build_eager_queryset(Book.objects.all(), BookWithAuthorCountrySerializer)

        self.assertEqual(qs.query.select_related, {'author': {'country': {}}})

    def test_dotted_source_field_chains_undeclared_relation(self):
        qs = build_eager_queryset(Location.objects.all(), LocationSerializer)

        self.assertIn('warehouse', qs.query.select_related)

    def test_dotted_source_field_resolves_with_zero_extra_queries(self):
        warehouse = Warehouse.objects.create(name='Central')
        Location.objects.create(code='A1', warehouse=warehouse)

        qs = build_eager_queryset(Location.objects.all(), LocationSerializer)

        with CaptureQueriesContext(connection) as ctx:
            fetched = qs.get(code='A1')
            _ = fetched.warehouse.name

        self.assertEqual(len(ctx.captured_queries), 1)

    def test_query_none_behaves_like_wildcard(self):
        with_none = build_eager_queryset(Book.objects.all(), BookSerializer, query=None)
        with_wildcard = build_eager_queryset(Book.objects.all(), BookSerializer, query={'*': True})

        self.assertEqual(with_none.query.select_related, with_wildcard.query.select_related)
        self.assertEqual(
            {p.prefetch_through for p in with_none._prefetch_related_lookups},
            {p.prefetch_through for p in with_wildcard._prefetch_related_lookups},
        )

    def test_query_trims_excluded_relation(self):
        query = {'pk': True, 'title': True, 'chapters': {'*': True}}
        qs = build_eager_queryset(Book.objects.all(), BookSerializer, query=query)

        lookups = {p.prefetch_through for p in qs._prefetch_related_lookups}
        self.assertEqual(lookups, {'chapters'})
        self.assertNotIn('author', qs.query.select_related or {})

    def test_query_only_pk_yields_no_eager_loading_at_all(self):
        qs = build_eager_queryset(Book.objects.all(), BookSerializer, query={'pk': True})

        self.assertEqual(qs.query.select_related, False)
        self.assertEqual(qs._prefetch_related_lookups, ())


class EagerRelationsFromColumnDefsTests(_SchemaBackedTestCase):
    def test_foreign_field_is_detected(self):
        column_defs = [{'name': 'author_name', 'foreign_field': 'author'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), ['author'])

    def test_column_name_matching_model_field_is_detected(self):
        column_defs = [{'name': 'author'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), ['author'])

    def test_dotted_foreign_field_uses_first_segment(self):
        column_defs = [{'name': 'author_country', 'foreign_field': 'author__country'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), ['author'])

    def test_non_matching_column_name_without_foreign_field_is_ignored(self):
        # This is the real gap found while migrating this from a consuming
        # project: a column whose `name` doesn't match any model field and
        # has no `foreign_field` (typically because it's not searchable) is
        # silently invisible to this helper.
        column_defs = [{'name': 'author_badge'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), [])

    def test_non_relation_field_is_ignored(self):
        column_defs = [{'name': 'title'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), [])

    def test_reverse_relation_is_not_included(self):
        # A table column always shows a scalar value -- reverse/M2M relations
        # are never select_related-able and shouldn't be picked up here.
        column_defs = [{'name': 'chapters'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), [])


class _RawQuerysetView:
    """Stands in for the DRF GenericAPIView tail of the MRO: provides the
    `get_queryset()` that `AutoEagerLoadingMixin.get_queryset()` delegates to
    via `super()`, exactly like `GenericAPIView.get_queryset()` would."""

    def __init__(self, queryset):
        self._raw_queryset = queryset

    def get_queryset(self):
        return self._raw_queryset


class _FakeViewSet(AutoEagerLoadingMixin, _RawQuerysetView):
    def __init__(self, request, serializer_class, queryset):
        super().__init__(queryset)
        self.request = request
        self.serializer_class = serializer_class

    def get_serializer_class(self):
        return self.serializer_class


class AutoEagerLoadingMixinTests(_SchemaBackedTestCase):
    def test_get_queryset_applies_eager_loading_without_query_param(self):
        request = RequestFactory().get('/books/')
        view = _FakeViewSet(request, BookAuthorWithoutLabelSerializer, Book.objects.all())

        qs = view.get_queryset()

        self.assertIn('author', qs.query.select_related)

    def test_get_queryset_respects_query_param(self):
        request = RequestFactory().get('/books/', {'query': '{pk}'})
        view = _FakeViewSet(request, BookAuthorWithoutLabelSerializer, Book.objects.all())

        qs = view.get_queryset()

        self.assertEqual(qs.query.select_related, False)

    def test_get_eager_queryset_can_be_called_directly_after_custom_filtering(self):
        # Mirrors a view with its own get_queryset() (search/filter params)
        # that just tacks eager loading onto the tail end.
        request = RequestFactory().get('/books/')
        view = _FakeViewSet(request, BookAuthorWithoutLabelSerializer, Book.objects.none())

        qs = view.get_eager_queryset(Book.objects.filter(title__icontains='a'))

        self.assertIn('author', qs.query.select_related)


class _RawAjaxDatatableView:
    model = None

    def __init__(self, model, queryset):
        self.model = model
        self._raw_queryset = queryset

    def get_initial_queryset(self, request=None):
        return self._raw_queryset


class _FakeAjaxDatatableView(AutoEagerLoadingAjaxDatatableMixin, _RawAjaxDatatableView):
    def __init__(self, model, queryset, column_defs=(), column_specs=None):
        super().__init__(model, queryset)
        self._column_defs = list(column_defs)

        if column_specs is not None:
            self.column_specs = column_specs

    def get_column_defs(self, request=None):
        return self._column_defs


class AutoEagerLoadingAjaxDatatableMixinTests(_SchemaBackedTestCase):
    def test_uses_cached_column_specs_without_calling_get_column_defs_again(self):
        calls = []

        class _TrackingView(_FakeAjaxDatatableView):
            def get_column_defs(self, request=None):
                calls.append(1)
                return super().get_column_defs(request)

        view = _TrackingView(
            Book,
            Book.objects.all(),
            column_specs=[{'name': 'author'}],
        )

        qs = view.get_initial_queryset(None)

        self.assertEqual(calls, [])
        self.assertIn('author', qs.query.select_related)

    def test_falls_back_to_get_column_defs_when_column_specs_missing(self):
        view = _FakeAjaxDatatableView(Book, Book.objects.all(), column_defs=[{'name': 'author'}])

        qs = view.get_initial_queryset(None)

        self.assertIn('author', qs.query.select_related)

    def test_eager_loading_relations_adds_relations_column_defs_cannot_expose(self):
        # Regression case found while migrating this: a column with
        # searchable=False and no foreign_field (name doesn't match the model
        # field) is invisible to eager_relations_from_column_defs -- this is
        # the declared escape hatch for it.
        class _View(_FakeAjaxDatatableView):
            eager_loading_relations = ['author']

        view = _View(Book, Book.objects.all(), column_defs=[{'name': 'author_badge'}])

        qs = view.get_initial_queryset(None)

        self.assertIn('author', qs.query.select_related)

    def test_eager_loading_select_properties_converts_relation_to_prefetch(self):
        class _View(_FakeAjaxDatatableView):
            eager_loading_select_properties = {'author': ['label']}

        view = _View(Book, Book.objects.all(), column_defs=[{'name': 'author'}])

        qs = view.get_initial_queryset(None)

        self.assertNotIn('author', qs.query.select_related or {})
        lookups = {p.prefetch_through for p in qs._prefetch_related_lookups}
        self.assertEqual(lookups, {'author'})

    def test_eager_loading_select_properties_resolves_with_zero_extra_queries(self):
        author = Author.objects.create(name='Jane')
        book = Book.objects.create(title='A Book', author=author)

        class _View(_FakeAjaxDatatableView):
            eager_loading_select_properties = {'author': ['label']}

        view = _View(Book, Book.objects.all(), column_defs=[{'name': 'author'}])

        with CaptureQueriesContext(connection) as ctx:
            qs = view.get_initial_queryset(None)
            fetched = qs.get(pk=book.pk)
            label = fetched.author.label

        self.assertEqual(label, 'Jane (author)')
        self.assertEqual(len(ctx.captured_queries), 2)

    def test_property_override_ignored_when_relation_not_actually_present(self):
        # eager_loading_select_properties references a relation that no
        # column exposed and eager_loading_relations didn't add either -- it
        # must be a silent no-op, not an error.
        class _View(_FakeAjaxDatatableView):
            eager_loading_select_properties = {'author': ['label']}

        view = _View(Book, Book.objects.all(), column_defs=[{'name': 'title'}])

        qs = view.get_initial_queryset(None)

        self.assertEqual(qs.query.select_related, False)
        self.assertEqual(qs._prefetch_related_lookups, ())


if __name__ == '__main__':
    unittest.main()
