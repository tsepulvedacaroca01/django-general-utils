from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.constants import LOOKUP_SEP
from ordered_model.models import OrderedModelQuerySet
from safedelete.config import FIELD_NAME
from safedelete.queryset import SafeDeleteQueryset

from ...utils.drf.validation_errors import ListValidationError


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

    def active(self):
        """ Return only active records"""
        return self.filter(is_active=True)

    def filter_queryable_property(self, **kwargs):
        """
        Set the filter to be used when querying queryable properties.
        """
        self.model._queryable_property_params = self.model._queryable_property_params | kwargs

        return self

    def bulk_create(self, objs, *args, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            errors = []

            for _obj in objs:
                try:
                    _obj.full_clean()
                    errors.append(ValidationError({}))
                except ValidationError as e:
                    errors.append(e)

            if any([len(_error.message_dict) > 0 for _error in errors]):
                raise ListValidationError(errors)

        response = super().bulk_create(objs, *args, **kwargs)

        return response

    def bulk_update(self, objs, *args, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            errors = []

            for _obj in objs:
                try:
                    _obj.full_clean()
                    errors.append(ValidationError({}))
                except ValidationError as e:
                    errors.append(e)

            if any([len(_error.message_dict) > 0 for _error in errors]):
                raise ListValidationError(errors)

        response = super().bulk_update(objs, *args, **kwargs)

        return response
