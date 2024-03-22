from collections import OrderedDict
from typing import Type

from django.core.exceptions import ObjectDoesNotExist
from django_restql.parser import QueryParser
from rest_framework import serializers

from ....utils.rest_ql import DynamicFieldsMixin


class PrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        self.only_pk = kwargs.pop('only_pk', False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if self.pk_field is not None:
            data = self.pk_field.to_internal_value(data)

        queryset = self.get_queryset()

        try:
            if isinstance(data, bool):
                raise TypeError

            if self.only_pk:
                if not queryset.filter(pk=data).exists():
                    self.fail('does_not_exist', pk_value=data)

                return data

            return queryset.get(pk=data)
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)


class NestedPrimaryKeyRelatedField(DynamicFieldsMixin, PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        """
        On read display a complete nested representation of the object(s)
        On write only require the PK (not an entire object) as value
        """
        self.serializer_class = kwargs.pop('serializer_class', None)
        self.extra_kwargs = kwargs.pop('extra_kwargs', {})
        self.only_internal_id = kwargs.pop('only_internal_id', False)
        super().__init__(**kwargs)

    def get_serializer_class(self) -> Type[serializers.ModelSerializer]:
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        assert self.serializer_class is not None, (
                "'%s' should either include a `get_serializer_class` attribute, "
                "or override the `get_serializer()` method."
                % self.__class__.__name__
        )

        return self.serializer_class

    def get_serializer(self, **kwargs) -> serializers.ModelSerializer:
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = self.get_serializer_class()
        restql_nested_parsed_queries = {}

        if hasattr(self.parent, 'restql_nested_parsed_queries'):
            restql_nested_parsed_queries = self.parent.restql_nested_parsed_queries

        parsed_query = restql_nested_parsed_queries.get(self.field_name, None)

        if parsed_query is None:
            parser = QueryParser()
            parsed_query = parser.parse('{*}')

        return serializer_class(
            **(kwargs | self.extra_kwargs | {
                'context': self.context,
                'parsed_query': parsed_query
            }))

    def use_pk_only_optimization(self):
        return False

    def to_representation(self, instance) -> dict:
        return self.get_serializer(instance=instance).data

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            # Ensure that field.choices returns something sensible
            # even when accessed with a read-only field.
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        return OrderedDict([
            (
                item.pk,
                self.display_value(item)
            )
            for item in queryset
        ])
