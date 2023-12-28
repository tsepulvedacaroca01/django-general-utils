from django.core.exceptions import FieldDoesNotExist
from django.db.models import Case, When, Value, BooleanField
from django.db.models import Q
from django.db.models.constants import LOOKUP_SEP
from django.db.models.functions import Now
from django.utils import timezone
from django_shared_property.decorator import shared_property
from ordered_model.models import OrderedModel, OrderedModelManager, OrderedModelQuerySet
from safedelete import SOFT_DELETE_CASCADE
from safedelete.config import FIELD_NAME, DELETED_INVISIBLE
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel
from safedelete.queryset import SafeDeleteQueryset

from .uuid import UUIDModel


class BaseModelQuerySet(SafeDeleteQueryset, OrderedModelQuerySet):
    def _is_valid_lookup(self, field_name: str):
        """
        Check if field_name is a valid lookup
        @param field_name:
        @return:
        """
        model = self.model

        for _index, _part in enumerate(field_name.split(LOOKUP_SEP)):
            try:
                field = model._meta.get_field(_part)
            except FieldDoesNotExist:
                return False

            if not field.is_relation:
                return False

            model = field.related_model

            # Final lookup, check if it's is_deleted boolean field
            try:
                model._meta.get_field(FIELD_NAME)
            except FieldDoesNotExist:
                return False

            # Not final lookup, continue with next one
            if _index < len(field_name.split(LOOKUP_SEP)) - 1:
                continue

            return True

        return False

    def _get_lookup_fields(self, fields: list) -> dict:
        """
        Get lookup fields from fields
        @param fields:
        @return:
        """
        lookup_fields = {}
        split_fields = []

        for _field in fields:
            _sum_field = ''

            for _index, _split_field in enumerate(_field.split(LOOKUP_SEP)):
                if _index == 0:
                    _sum_field += _split_field
                else:
                    _sum_field += f'__{_split_field}'

                split_fields.append(_sum_field)

        for _field in split_fields:
            if not self._is_valid_lookup(_field):
                continue

            lookup_fields[f'{_field}__{FIELD_NAME}__isnull'] = True

        return lookup_fields

    def _set_filter_from_source_expressions(self, field) -> None:
        """
        Set filter from source expressions
        @param field:
        @return:
        """
        if not hasattr(field, 'get_source_expressions') or not callable(field.get_source_expressions):
            return None

        for _expression in field.get_source_expressions():
            # If the expression is a Q | Coalesce | When | etc, object, we need to iterate over its children
            self._set_filter_from_source_expressions(_expression)

            if not hasattr(_expression, 'name') or not hasattr(field, 'filter'):
                continue

            for _filter in self._get_lookup_fields([_expression.name]).keys():
                extra_filter = Q(**{_filter: True})

                if not field.filter:
                    field.filter = extra_filter
                    continue

                if _filter not in dict(field.filter.children):
                    field.filter &= extra_filter

        return None

    def filter(self, *args, **kwargs):
        """
        Filter with lookup fields
        @return:
        """
        kwargs.update(self._get_lookup_fields(kwargs.keys()))

        for _key, _value in kwargs.items():
            kwargs[_key] = _value

        return super().filter(*args, **kwargs)

    def annotate(self, force_deleted: bool = True, *args, **kwargs):
        """
        Return a query set in which the returned objects have been annotated
        with extra data or aggregations to filter the deleted ones.
        @param force_deleted: Force if deleted objects will be taken into account.
        """
        if not force_deleted or not self.query._safedelete_visibility == DELETED_INVISIBLE:
            return super().annotate(*args, **kwargs)

        for key, value in kwargs.items():
            self._set_filter_from_source_expressions(kwargs[key])

        return super().annotate(*args, **kwargs)

class BaseModelManager(SafeDeleteManager, OrderedModelManager):
    pass


class BaseModel(SafeDeleteModel, OrderedModel, UUIDModel):
    _safedelete_policy = SOFT_DELETE_CASCADE
    objects = BaseModelManager(BaseModelQuerySet)

    class Meta:
        abstract = True
        ordering = ('-id',)

    @shared_property(
        Case(
            When(**{f'{FIELD_NAME}__lt': Now(), 'then': Value(True)}),
            default=Value(False),
            output_field=BooleanField()
        ),
    )
    def is_deleted(self):
        return getattr(self, FIELD_NAME) is not None and getattr(self, FIELD_NAME) < timezone.now()

    def save(self, keep_deleted=False, **kwargs):
        if not keep_deleted:
            if getattr(self, FIELD_NAME) and self.pk:
                # if the object was undeleted, we need to reset the order
                self.order = self.get_ordering_queryset().get_next_order()

        super().save(keep_deleted, **kwargs)
