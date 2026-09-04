from django.core.exceptions import FieldDoesNotExist
from django.db.models import Prefetch, QuerySet
from django_restql.mixins import EagerLoadingMixin as RestqlEagerLoadingMixin
from django_restql.mixins import RequestQueryParserMixin
from queryable_properties.properties.base import QueryablePropertyDescriptor
from rest_framework import serializers


def _is_many(field) -> bool:
    return isinstance(field, (serializers.ListSerializer, serializers.ManyRelatedField))


def _resolve_nested_serializer_class(field):
    """
    Resolves the nested serializer class of a relation field.

    `LazyRefSerializerField(many=True)` is a special case: `many_init`
    (see `fields/lazy_ref_field.py`) resolves `.child` eagerly to an
    *already-built instance* of the nested serializer (it calls
    `.get_serializer()` instead of leaving the `LazyRefSerializerField`
    unresolved) — so it doesn't expose `get_serializer_class()` and the
    class has to be pulled off with `type()`. `NestedPrimaryKeyRelatedField
    (many=True)` instead gets wrapped in a standard DRF `ManyRelatedField`,
    whose `child_relation` is still the original field instance (with
    `get_serializer_class()` available).
    """
    if isinstance(field, serializers.ListSerializer):
        return type(field.child)

    if isinstance(field, serializers.ManyRelatedField):
        field = field.child_relation

    get_serializer_class = getattr(field, 'get_serializer_class', None)
    return get_serializer_class() if get_serializer_class else None


def _effective_fields(field) -> set | None:
    """
    Ceiling of fields the nested serializer can ever render, independent of
    what `?query=` asks for. `extra_kwargs={'fields': [...]}` is the only way
    `LazyRefSerializerField`/`NestedPrimaryKeyRelatedField` declare this; when
    absent, `None` means no ceiling (the nested serializer can render any of
    its `Meta.fields`).

    - `many=True` case: `field.child` is already the built instance of the
      nested serializer (see `_resolve_nested_serializer_class`), so the
      `fields=[...]` that came from `extra_kwargs` ended up in
      `dynamic_fields_mixin_kwargs['fields']` (`django_restql.DynamicFieldsMixin`
      stores it there in `__init__`).
    - Single case: `field`/`field.child_relation` hasn't built the nested
      serializer yet (it's lazy) — `fields=[...]` lives in
      `field.extra_kwargs['fields']`.
    """
    if isinstance(field, serializers.ListSerializer):
        restriction = field.child.dynamic_fields_mixin_kwargs.get('fields')
    else:
        singular = field.child_relation if isinstance(field, serializers.ManyRelatedField) else field
        restriction = getattr(singular, 'extra_kwargs', {}).get('fields')

    return set(restriction) if restriction else None


def _query_node(query: dict, field_name: str):
    """
    Resolves the node of the parsed restql `query` for `field_name`:
    True/False (included/excluded leaf), a dict (included with a
    sub-selection), or `{'*': True}` propagated downward when the client
    didn't restrict that level.
    """
    if field_name in query:
        return query[field_name]

    if query.get('*'):
        return {'*': True}

    return False


def _restrict_query(query: dict, allowed_fields: set | None) -> dict:
    """
    Applies the `_effective_fields` ceiling on an already-resolved `query` —
    without this, a field excluded via `extra_kwargs={'fields': [...]}` (e.g.
    a queryable_property that a parent field's nested serializer never asks
    for) still counts as "included by default" and forces optimizations
    (`select_properties`, `Prefetch`) that are never actually used when
    rendering.
    """
    if allowed_fields is None:
        return query

    if query.get('*'):
        return {name: True for name in allowed_fields}

    return {k: v for k, v in query.items() if k in allowed_fields}


def _queryable_property_names(model, serializer_class, query: dict) -> list[str]:
    """
    Names declared in `Meta.fields` that aren't a serializer field of their
    own (not in `_declared_fields`), resolve to a model `@queryable_property`,
    and are effectively included in `query` — added to `select_properties(...)`
    so the annotation travels with the `Prefetch`.
    """
    declared_fields = getattr(serializer_class, '_declared_fields', {})
    names = []

    for field_name in getattr(serializer_class.Meta, 'fields', ()):
        if field_name in declared_fields or _query_node(query, field_name) is False:
            continue

        if isinstance(getattr(model, field_name, None), QueryablePropertyDescriptor):
            names.append(field_name)

    return names


def _dotted_source_relations(model, serializer_class, query: dict) -> list[str]:
    """
    Detects plain fields declared with `source='relation.field'` (e.g.
    `serializers.CharField(source='warehouse.name')`) and chains the relation
    into `select_related`, as long as it's a forward to-one relation and the
    field is effectively included in `query`.

    Known limit: doesn't cover `SerializerMethodField` — there's no way to
    introspect which relation the method touches without running it, so a
    method that walks an FK without `select_related` still causes a silent
    N+1.
    """
    declared_fields = getattr(serializer_class, '_declared_fields', {})
    names = []

    for field_name, field in declared_fields.items():
        source = getattr(field, 'source', None) or field_name

        if '.' not in source or _query_node(query, field_name) is False:
            continue

        head = source.split('.')[0]

        try:
            model_field = model._meta.get_field(head)
        except FieldDoesNotExist:
            continue

        if getattr(model_field, 'is_relation', False) and (
            getattr(model_field, 'many_to_one', False) or getattr(model_field, 'one_to_one', False)
        ):
            names.append(head)

    return names


def _collect_eager_spec(model, serializer_class, query: dict) -> tuple[list[str], list[Prefetch], list[str]]:
    """
    Computes (without touching any queryset) the three eager-loading pieces
    for `model`/`serializer_class`, recursing both into relations to
    prefetch (`is_many`/reverse/M2M) and into relations chained onto
    `select_related` (forward to-one) — this second case is what requires
    separating "compute" from "apply": a chain like `location__warehouse`
    (needed by a `source='warehouse.name'` field nested inside an
    already-`select_related`-ed relation) can only be built as a *string*,
    not by calling `.select_related()` on an intermediate queryset.
    """
    declared_fields = getattr(serializer_class, '_declared_fields', {})

    select_related: list[str] = []
    prefetch_related: list[Prefetch] = []

    for field_name, field in declared_fields.items():
        node = _query_node(query, field_name)

        if node is False:
            continue

        try:
            model_field = model._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue

        if not getattr(model_field, 'is_relation', False):
            continue

        is_many = _is_many(field)
        nested_serializer_class = _resolve_nested_serializer_class(field)
        is_to_one = bool(getattr(model_field, 'many_to_one', False) or getattr(model_field, 'one_to_one', False))
        related_model = model_field.related_model
        nested_query = node if isinstance(node, dict) else {'*': True}
        nested_query = _restrict_query(nested_query, _effective_fields(field))

        # `select_properties()` rejects paths with a `relation_path`
        # ("Cannot select properties on related models.") — there's no way
        # to annotate a related model's @queryable_property onto a
        # select_related JOIN. If the nested serializer asks for (and will
        # actually render, per `nested_query` already trimmed by
        # extra_kwargs) a queryable_property of its own, that branch can't
        # be resolved via select_related and gets forced into Prefetch —
        # Django does support Prefetch(queryset=...) on forward (to-one)
        # relations, not just reverse/M2M, and the annotation caches
        # correctly on the nested instance (verified empirically).
        own_props = (
            _queryable_property_names(related_model, nested_serializer_class, nested_query)
            if nested_serializer_class else []
        )

        if is_many or not is_to_one or own_props:
            related_qs = related_model.objects.all()

            if nested_serializer_class is not None:
                related_qs = build_eager_queryset(related_qs, nested_serializer_class, nested_query)

            prefetch_related.append(Prefetch(field_name, queryset=related_qs))
        else:
            select_related.append(field_name)

            if nested_serializer_class is not None:
                nested_select, nested_prefetch, _nested_props = _collect_eager_spec(
                    related_model, nested_serializer_class, nested_query,
                )
                select_related.extend(f'{field_name}__{path}' for path in nested_select)

                for prefetch in nested_prefetch:
                    prefetch.add_prefix(field_name)
                    prefetch_related.append(prefetch)

    select_related.extend(_dotted_source_relations(model, serializer_class, query))
    props = _queryable_property_names(model, serializer_class, query)

    return select_related, prefetch_related, props


def build_eager_queryset(queryset: QuerySet, serializer_class, query: dict = None) -> QuerySet:
    """
    Automatically applies select_related/prefetch_related/select_properties,
    derived from the relation fields declared on `serializer_class`
    (`NestedPrimaryKeyRelatedField` / `LazyRefSerializerField` — see
    `django_general_utils.utils.drf.fields`), from the `@queryable_property`
    names listed in `Meta.fields`, and from the fields actually requested in
    `query` (a dict already normalized via
    `django_restql.mixins.EagerLoadingMixin.get_dict_parsed_restql_query`;
    `None` means include everything — the default behavior without a
    `?query=` param on the request).

    No per-view select_related/prefetch_related dict to keep in sync — the
    ORM strategy (`select_related` vs `prefetch_related`) is derived from
    `model._meta.get_field(field_name)` (forward to-one vs reverse/many, or a
    forward to-one relation with its own queryable_property, which forces
    `Prefetch` because `select_properties()` doesn't support paths into
    related models), and the depth is derived recursively from each field's
    nested `serializer_class`.

    Only works with relation fields that expose a resolvable nested
    serializer class this way — a `SerializerMethodField` that walks a
    relation is invisible to this introspection (same limit as
    `_dotted_source_relations`, see its docstring).
    """
    model = queryset.model
    query = query if query is not None else {'*': True}
    select_related, prefetch_related, props = _collect_eager_spec(model, serializer_class, query)

    if select_related:
        queryset = queryset.select_related(*set(select_related))

    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)

    if props:
        queryset = queryset.select_properties(*props)

    return queryset


class AutoEagerLoadingMixin(RequestQueryParserMixin):
    """
    ViewSet mixin — exposes `get_eager_queryset(queryset)`, which applies
    `build_eager_queryset` using `self.get_serializer_class()` and the
    current request's `?query=` (django-restql) param (no `?query=` from the
    client means include everything — same behavior as without this mixin).

    Also overrides `get_queryset()`: if the view doesn't define its own
    `get_queryset()` (or defines one that calls `super().get_queryset()`
    before filtering), there's no need to write `Model.objects.all()` by
    hand — declaring `queryset = Model.objects.all()` as a class attribute,
    like any plain `GenericAPIView`, is enough. MRO matters: this mixin must
    come before `GenericViewSet`/`mixins.*ModelMixin` in the inheritance list
    (`class XViewSet(AutoEagerLoadingMixin, mixins.ListModelMixin, ...,
    viewsets.GenericViewSet)`) so that `super().get_queryset()` reaches
    `GenericAPIView.get_queryset()` (resolves `self.queryset`) before this
    method applies eager loading to it.

    A view with its own filtering (search, querystring params) still writes
    a normal `get_queryset()` and only changes the tail end: instead of
    chaining `select_related`/`prefetch_related` by hand, it calls
    `self.get_eager_queryset(qs)` — Python resolves the subclass's own method
    before this mixin's, so there's no conflict.
    """

    def get_eager_queryset(self, queryset: QuerySet) -> QuerySet:
        query = None

        if self.has_restql_query_param(self.request):
            parsed = self.get_parsed_restql_query_from_req(self.request)
            query = RestqlEagerLoadingMixin.get_dict_parsed_restql_query(parsed)

        return build_eager_queryset(queryset, self.get_serializer_class(), query)

    def get_queryset(self) -> QuerySet:
        return self.get_eager_queryset(super().get_queryset())


def eager_relations_from_column_defs(model, column_defs) -> list[str]:
    """
    Derives select_related for an `AjaxDatatableView` from `get_column_defs()`
    instead of a DRF serializer (there isn't one here).

    Unlike `build_eager_queryset` (which introspects
    `serializer_class._declared_fields`), this helper reads the metadata
    `AjaxDatatableView` already requires for each column's search/filter to
    work: `foreign_field` (when the column name doesn't match the model
    field, e.g. `company_name` -> `foreign_field: 'company'`) or the
    column's own `name` (when it does match, e.g. `created_by`). This is not
    free-form code introspection — it depends on every relation used in
    `customize_row` having a column in `get_column_defs` that references it,
    which is the pattern `AjaxDatatableView` already needs for columns to be
    searchable/orderable/filterable.

    Known limit — the same kind of gap as a `SerializerMethodField`: if
    `customize_row` uses a relation that has NO column of its own in
    `get_column_defs` (e.g. a relation only shown as supporting text, never
    searchable/filterable), this helper won't detect it. Doesn't cover
    reverse/M2M (a table column always shows a scalar value, never a list) —
    only forward to-one, via `select_related`.
    """
    names = set()

    for column in column_defs:
        candidate = column.get('foreign_field') or column.get('name')

        if not candidate:
            continue

        head = candidate.split('__')[0]

        try:
            model_field = model._meta.get_field(head)
        except FieldDoesNotExist:
            continue

        if getattr(model_field, 'is_relation', False) and (
            getattr(model_field, 'many_to_one', False) or getattr(model_field, 'one_to_one', False)
        ):
            names.add(head)

    return sorted(names)


class AutoEagerLoadingAjaxDatatableMixin:
    """
    Automatically applies `select_related` in `get_initial_queryset()`,
    derived from `get_column_defs()` (`eager_relations_from_column_defs`) —
    no line to maintain by hand, no risk of it drifting out of sync when a
    new FK column is added.

    Verified at no extra cost: `AjaxDatatableView.dispatch()` (base library)
    already calls `get_column_defs()` once in `initialize()` and caches the
    normalized result in `self.column_specs` — this mixin reuses that
    instead of calling `get_column_defs()` again (which runs its own queries
    to build filter choices; calling it twice would cost double). Falls back
    to `get_column_defs(request)` only if `get_initial_queryset` is invoked
    outside the normal request cycle (e.g. a test that doesn't go through
    `dispatch()`/`initialize()` first), where `self.column_specs` doesn't
    exist yet.

    Limit inherited from `eager_relations_from_column_defs`: a relation used
    in `customize_row()` without its own column in `get_column_defs()` isn't
    detected — check for this before applying the mixin to an existing view,
    don't assume adding it is enough. `eager_loading_relations` covers
    exactly this case: relations `customize_row()` uses that no column
    declares (because they're not searchable/filterable, not because
    `foreign_field` was forgotten):

        eager_loading_relations = ['company', 'status', 'address']

    These are added to the result of `eager_relations_from_column_defs`
    before applying `select_related`/`eager_loading_select_properties` — it
    doesn't replace the automatic derivation, it completes it.

    `eager_loading_select_properties` — unlike `select_related`, this
    **can't be derived** from `get_column_defs()`: there's no declarative
    place (equivalent to a DRF serializer's `Meta.fields`) that says which
    `@queryable_property` of a relation `customize_row()` uses. It's the same
    limit as a `SerializerMethodField` — imperative code, not introspectable
    — except this one is a real, observed case, not a hypothetical: a view
    accessing `obj.created_by.full_name` (a queryable_property on the related
    user model) with `created_by` in `select_related` triggers one extra
    query per row for `full_name`, because `select_properties()` doesn't
    support paths into related models ("Cannot select properties on related
    models.", same limit documented for the `build_eager_queryset` case
    above). Declared by hand, per relation:

        eager_loading_select_properties = {'created_by': ['full_name']}

    The mixin converts that specific relation from `select_related` to
    `Prefetch(..., queryset=Model.objects.select_properties(...))` — same
    mechanism verified for the DRF case (`Prefetch` does work on forward
    to-one relations, not just reverse/M2M).
    """

    eager_loading_select_properties: dict = {}
    eager_loading_relations: list = []

    def get_initial_queryset(self, request=None):
        queryset = super().get_initial_queryset(request)
        column_defs = getattr(self, 'column_specs', None) or self.get_column_defs(request)
        relations = set(eager_relations_from_column_defs(self.model, column_defs))
        relations.update(self.eager_loading_relations)
        property_overrides = self.eager_loading_select_properties

        select_related = [name for name in relations if name not in property_overrides]
        prefetch_related = []

        for relation_name, prop_names in property_overrides.items():
            if relation_name not in relations:
                continue

            model_field = self.model._meta.get_field(relation_name)
            related_qs = model_field.related_model.objects.select_properties(*prop_names)
            prefetch_related.append(Prefetch(relation_name, queryset=related_qs))

        if select_related:
            queryset = queryset.select_related(*select_related)

        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)

        return queryset
