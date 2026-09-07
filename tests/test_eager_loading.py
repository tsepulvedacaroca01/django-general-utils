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


class Cover(BaseV3):
    # The FK lives here, but the interesting side for eager_relations_from_column_defs is
    # Book's *reverse* accessor ('cover') -- a `OneToOneRel`, which unlike a concrete field
    # has no `attname`.
    image_url = models.CharField(max_length=64, null=True, blank=True)
    book = models.OneToOneField(Book, on_delete=models.CASCADE, related_name='cover')

    class Meta(BaseV3.Meta):
        app_label = 'auth'
        db_table = 'test_el_cover'


_MODELS = (Country, Author, Book, Chapter, Review, Warehouse, Location, Cover)


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


class ChapterEditorIdSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """
    Regression fixture: a plain `PrimaryKeyRelatedField` explicitly declared
    under a name that matches the FK's *attname*, not its real relation name
    (`editor_id` vs. `editor`) -- the common "expose just the id" pattern.
    `Model._meta.get_field()` resolves "editor_id" too (it matches forward
    FK/O2O fields by attname, not just by name), so this field used to reach
    the to-one branch of `_collect_eager_spec` and get treated as a relation
    to eager-load.
    """

    editor_id = serializers.PrimaryKeyRelatedField(source='editor', queryset=Author.objects.all())

    class Meta:
        model = Chapter
        fields = ('pk', 'title', 'editor_id')


class BookPlainReviewIdsSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """
    A plain (non-nested) `PrimaryKeyRelatedField(many=True)` -- no
    `get_serializer_class()`, same as the to-one case above, but this one
    *does* need a `Prefetch` (accessing `.reviews.all()` to list the PKs
    still costs a query per row without one). Confirms the "nothing to
    eager-load" skip added for the to-one case doesn't over-fire here.
    """

    reviews = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Book
        fields = ('pk', 'title', 'reviews')


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


class BookDownloadSerializer(DynamicFieldsMixin, serializers.Serializer):
    """
    Regression fixture: a plain `serializers.Serializer` (not `ModelSerializer`) for an
    action-specific endpoint (e.g. a download/export action) that isn't a 1:1 model
    representation -- has no `Meta` at all, unlike every other fixture in this file.
    """
    book = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all(), required=True)
    file_name = serializers.SerializerMethodField()

    def get_file_name(self, instance) -> str:
        return 'export.xlsx'


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

    def test_plain_related_field_with_mismatched_name_is_skipped_not_crashed(self):
        # Regression: `editor_id` (source="editor") used to reach the to-one
        # branch and get passed straight to `select_related()` as-is --
        # Django raised `FieldError: Invalid field name(s) given in
        # select_related` for "editor_id" (the model's real field is
        # "editor"). A plain PrimaryKeyRelatedField never needs
        # select_related in the first place (DRF's own pk-only optimization
        # already avoids the extra query), so the fix is to skip it entirely.
        qs = build_eager_queryset(Chapter.objects.all(), ChapterEditorIdSerializer)

        self.assertEqual(qs.query.select_related, False)
        self.assertEqual(qs._prefetch_related_lookups, ())

    def test_plain_related_field_with_mismatched_name_executes_without_error(self):
        author = Author.objects.create(name='Jane')
        book = Book.objects.create(title='A Book', author=author)
        Chapter.objects.create(title='Ch1', book=book, editor=author)

        qs = build_eager_queryset(Chapter.objects.all(), ChapterEditorIdSerializer)

        # Building the queryset alone doesn't validate field names -- only
        # compiling/executing it does. The regression only shows up here.
        fetched = list(qs)

        self.assertEqual(len(fetched), 1)

    def test_plain_serializer_without_meta_does_not_crash(self):
        # Regression: a plain `serializers.Serializer` (no `Meta` at all --
        # the common shape for an action-specific download/export endpoint
        # that isn't a 1:1 model representation) crashed with
        # `AttributeError: type object '...' has no attribute 'Meta'` as soon
        # as _queryable_property_names accessed `serializer_class.Meta`
        # directly. Real case: ProductStockHistoryDownloadSerializer in a
        # consuming project, hit via AutoEagerLoadingMixin.get_queryset().
        qs = build_eager_queryset(Book.objects.all(), BookDownloadSerializer)

        fetched = list(qs)

        self.assertEqual(fetched, [])

    def test_plain_many_related_field_still_uses_prefetch_related(self):
        # Same "no nested serializer class" shape as the to-one case above,
        # but `many=True` -- must still go through Prefetch (accessing
        # `.reviews.all()` for the PK list costs a query per row otherwise),
        # not get caught by the to-one skip.
        qs = build_eager_queryset(Book.objects.all(), BookPlainReviewIdsSerializer)

        lookups = {p.prefetch_through for p in qs._prefetch_related_lookups}
        self.assertEqual(lookups, {'reviews'})


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

    def test_column_named_after_fk_attname_resolves_to_real_relation_name(self):
        # Regression: a column named after the FK's *attname* ('editor_id')
        # used to be added to the result verbatim instead of resolved to the
        # real relation name ('editor'). The base AjaxDatatableView's generic
        # render does `getattr(instance, 'editor_id')` -- a local column, no
        # query -- so this doesn't even need select_related, but when it WAS
        # added, `select_related('editor_id')` blew up with FieldError since
        # 'editor_id' isn't a real field/relation name.
        column_defs = [{'name': 'editor_id'}]

        self.assertEqual(eager_relations_from_column_defs(Chapter, column_defs), [])

    def test_column_named_after_real_relation_name_still_detected(self):
        # Same FK, but the column name matches the actual relation name
        # ('editor', not 'editor_id') -- this is the case that genuinely
        # needs select_related, since the generic render returns the related
        # object itself.
        column_defs = [{'name': 'editor'}]

        self.assertEqual(eager_relations_from_column_defs(Chapter, column_defs), ['editor'])

    def test_foreign_field_matching_attname_is_skipped(self):
        # Same bug, reached through the other entry point: `foreign_field`
        # (not just `name`) can also be set to an FK's attname, e.g. a
        # searchable column labeled 'editor_display' backed by
        # foreign_field='editor_id'.
        column_defs = [{'name': 'editor_display', 'foreign_field': 'editor_id'}]

        self.assertEqual(eager_relations_from_column_defs(Chapter, column_defs), [])

    def test_dotted_foreign_field_with_attname_head_is_skipped(self):
        # `head` is only the first segment of a dotted foreign_field -- must
        # be checked against attname/name the same way as the undotted case.
        column_defs = [{'name': 'editor_display', 'foreign_field': 'editor_id__name'}]

        self.assertEqual(eager_relations_from_column_defs(Chapter, column_defs), [])

    def test_reverse_one_to_one_column_is_detected_without_crashing(self):
        # Regression: a reverse one-to-one (`OneToOneRel`, e.g. Book.cover)
        # has no `attname` at all -- only concrete fields on the FK-holding
        # side do. The attname-skip check must default missing attname to
        # None instead of a plain attribute access, or this raises
        # AttributeError before it ever gets to select_related().
        column_defs = [{'name': 'cover'}]

        self.assertEqual(eager_relations_from_column_defs(Book, column_defs), ['cover'])


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

    def test_get_queryset_with_meta_less_serializer_does_not_crash(self):
        # End-to-end version of test_plain_serializer_without_meta_does_not_crash: the real
        # crash happened through this exact call chain (ViewSet.get_queryset() ->
        # AutoEagerLoadingMixin.get_queryset() -> get_eager_queryset() -> build_eager_queryset()),
        # for a `get_serializer_class()` that returns a plain Serializer for one action (e.g. a
        # detail-route download action) while the ViewSet's model-bound `serializer_class` stays
        # a normal ModelSerializer.
        request = RequestFactory().get('/books/1/download/')
        view = _FakeViewSet(request, BookDownloadSerializer, Book.objects.all())

        qs = view.get_queryset()

        self.assertEqual(list(qs), [])


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

    def test_column_named_after_fk_attname_is_skipped_not_crashed(self):
        # Mirrors test_plain_related_field_with_mismatched_name_is_skipped_not_crashed
        # on the DRF side: a column named 'editor_id' must not be turned into
        # select_related('editor_id') -- that's not a valid relation name and
        # would raise FieldError as soon as the queryset is executed.
        view = _FakeAjaxDatatableView(Chapter, Chapter.objects.all(), column_defs=[{'name': 'editor_id'}])

        qs = view.get_initial_queryset(None)

        self.assertEqual(qs.query.select_related, False)

    def test_column_named_after_fk_attname_executes_without_error(self):
        # Building the queryset alone doesn't validate field names -- only
        # compiling/executing it does. The regression only shows up here.
        book = Book.objects.create(title='A Book', author=Author.objects.create(name='Jane'))
        Chapter.objects.create(title='Chapter 1', book=book)

        view = _FakeAjaxDatatableView(Chapter, Chapter.objects.all(), column_defs=[{'name': 'editor_id'}])

        qs = view.get_initial_queryset(None)
        fetched = list(qs)

        self.assertEqual(len(fetched), 1)

    def test_reverse_one_to_one_column_executes_without_error(self):
        # End-to-end version of test_reverse_one_to_one_column_is_detected_without_crashing:
        # confirms get_initial_queryset() doesn't just build without raising, but that the
        # resulting select_related('cover') actually executes -- a real case found in
        # shipped-django (TransferLocation.work_order).
        author = Author.objects.create(name='Jane')
        book = Book.objects.create(title='A Book', author=author)
        Cover.objects.create(book=book, image_url='cover.png')

        view = _FakeAjaxDatatableView(Book, Book.objects.all(), column_defs=[{'name': 'cover'}])

        qs = view.get_initial_queryset(None)
        fetched = list(qs)

        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0].cover.image_url, 'cover.png')

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
