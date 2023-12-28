from typing import Type

from django_restql.parser import QueryParser
from rest_framework import serializers

from ....utils.rest_ql import DynamicFieldsMixin


class NestedPrimaryKeyRelatedField(DynamicFieldsMixin, serializers.PrimaryKeyRelatedField):
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

    def to_internal_value(self, data: int):
        """
        Check if return id or instance
        @returns: int or instance
        """
        instance = super(NestedPrimaryKeyRelatedField, self).to_internal_value(data)

        if self.only_internal_id:
            return instance.id

        return instance

    def use_pk_only_optimization(self) -> bool:
        return False

    def to_representation(self, instance) -> dict:
        return self.get_serializer(instance=instance).data
