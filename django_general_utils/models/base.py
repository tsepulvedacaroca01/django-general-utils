from copy import copy

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Case, When, Value, BooleanField, Q, TextField, Manager
from django.db.models.constants import LOOKUP_SEP
from django.db.models.functions import Now
from ordered_model.models import OrderedModel, OrderedModelManager, OrderedModelQuerySet
from queryable_properties import managers
from queryable_properties.properties import queryable_property
from safedelete import SOFT_DELETE_CASCADE
from safedelete.config import FIELD_NAME, DELETED_INVISIBLE
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel
from safedelete.queryset import SafeDeleteQueryset

from .uuid import UUIDModel
from ..utils.image.blur_img_to_base64 import blur_img_to_base64, DEFAULT_BLUR_CODE


def set_blur_fields(cls):
    fields = getattr(cls, '_images_field_to_blur')
    suffix = getattr(cls, '_suffix_blur_code')

    for _field in fields:
        cls.add_to_class(
            f'{_field}_{suffix}',
            TextField(
                editable=False,
                default=DEFAULT_BLUR_CODE
            )
        )

    return cls


class BaseModelQuerySet(SafeDeleteQueryset, OrderedModelQuerySet):
    @staticmethod
    def _is_valid_lookup(model, field_name: str):
        """
        Check if field_name is a valid lookup
        @param field_name:
        @return:
        """
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

    @staticmethod
    def get_lookup_fields(model, fields: list) -> dict:
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
            if not BaseModelQuerySet._is_valid_lookup(model, _field):
                continue

            lookup_fields[f'{_field}__{FIELD_NAME}__isnull'] = True

        return lookup_fields

    @staticmethod
    def set_filter_from_source_expressions(model, field) -> None:
        """
        Set filter from source expressions
        @param field:
        @return:
        """
        if not hasattr(field, 'get_source_expressions') or not callable(field.get_source_expressions):
            return None

        for _expression in field.get_source_expressions():
            # If the expression is a Q | Coalesce | When | etc, object, we need to iterate over its children
            BaseModelQuerySet.set_filter_from_source_expressions(model, _expression)

            if not hasattr(_expression, 'name') or not hasattr(field, 'filter'):
                continue

            for _filter in BaseModelQuerySet.get_lookup_fields(model, [_expression.name]).keys():
                extra_filter = Q(**{_filter: True})

                if not field.filter:
                    field.filter = extra_filter
                    continue

                if _filter not in dict(field.filter.children):
                    field.filter &= extra_filter

        return field

    def filter(self, *args, **kwargs):
        """
        Filter with lookup fields
        @return:
        """
        kwargs.update(
            self.get_lookup_fields(
                self.model,
                kwargs.keys()
            )
        )

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

        for _key, _value in kwargs.items():
            kwargs[_key] = self.set_filter_from_source_expressions(self.model, _value)

        return super().annotate(*args, **kwargs)

    def _values(self, *fields, **expressions):
        clone = self._chain()
        if expressions:
            clone = clone.annotate(**expressions)

        clone = clone.filter(**self.get_lookup_fields(self.model, fields))
        clone._fields = fields
        clone.query.set_values(fields)

        return clone


class BaseModelManager(SafeDeleteManager, OrderedModelManager):
    pass


class QueryablePropertiesManagerMixin(managers.QueryablePropertiesManagerMixin):
    @classmethod
    def apply_to(cls, manager):
        """
        Copy the given manager and apply this mixin (and thus queryable
        properties functionality) to it, returning a new manager that allows
        to use queryable property interaction.

        :param Manager manager: The manager to apply this mixin to.
        :return: A copy of the given manager with queryable properties
                 functionality.
        :rtype: QueryablePropertiesManager
        """
        manager = copy(manager)
        # manager.name = '<{}_with_queryable_properties>'.format(getattr(manager, 'name', None) or 'manager')
        return cls.inject_into_object(manager)


class BaseModel(SafeDeleteModel, OrderedModel, UUIDModel):
    _images_field_to_blur = []
    _suffix_blur_code = 'blur_code'
    _safedelete_policy = SOFT_DELETE_CASCADE
    objects = QueryablePropertiesManagerMixin.apply_to(BaseModelManager(BaseModelQuerySet))

    class Meta:
        abstract = True
        ordering = ('-id',)

    @queryable_property(annotation_based=True)
    @classmethod
    def is_deleted(cls):
        return Case(
            When(**{f'{FIELD_NAME}__lt': Now(), 'then': Value(True)}),
            default=Value(False),
            output_field=BooleanField()
        )

    def set_blur_image(self, field: str) -> None:
        """
        _set_blur_image
        @return:
        """
        setattr(
            self,
            f'{field}_{self._suffix_blur_code}',
            blur_img_to_base64(getattr(self, field))
        )

        return None

    def save(self, keep_deleted=False, **kwargs):
        if not keep_deleted:
            if getattr(self, FIELD_NAME) and self.pk:
                # if the object was undeleted, we need to reset the order
                self.order = self.get_ordering_queryset().get_next_order()

        for _field in self._images_field_to_blur:
            self.set_blur_image(_field)

        self.full_clean(validate_constraints=False)

        super().save(keep_deleted, **kwargs)

    def clean(self) -> None:
        """
        Additional validations
        @return: None
        """
        self.validate_constraints()

        if getattr(self, FIELD_NAME) is not None:
            return None

        return None
