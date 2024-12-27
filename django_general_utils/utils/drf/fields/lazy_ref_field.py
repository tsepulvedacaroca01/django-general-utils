from django.utils.module_loading import import_string
from django_restql.parser import QueryParser
from rest_framework import serializers
from rest_framework.serializers import LIST_SERIALIZER_KWARGS, LIST_SERIALIZER_KWARGS_REMOVE

from ....utils.rest_ql import DynamicFieldsMixin


class LazyRefSerializerField(DynamicFieldsMixin, serializers.BaseSerializer):
    def __init__(self, **kwargs):
        self.serializer_class = kwargs.pop('serializer_class', None)
        self.extra_kwargs = kwargs.pop('extra_kwargs', {})

        super().__init__(**kwargs)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """
        This method implements the creation of a `ListSerializer` parent
        class when `many=True` is used. You can customize it if you need to
        control which keyword arguments are passed to the parent, and
        which are passed to the child.

        Note that we're over-cautious in passing most arguments to both parent
        and child classes in order to try to cover the general case. If you're
        overriding this method you'll probably want something much simpler, eg:

        @classmethod
        def many_init(cls, *args, **kwargs):
            kwargs['child'] = cls()
            return CustomListSerializer(*args, **kwargs)
        """
        list_kwargs = {}

        for key in LIST_SERIALIZER_KWARGS_REMOVE:
            value = kwargs.pop(key, None)
            if value is not None:
                list_kwargs[key] = value

        # Usamos el método get_serializer_class para obtener la clase del serializador
        list_kwargs['child'] = cls(*args, **kwargs).get_serializer()
        list_kwargs.update({
            key: value for key, value in kwargs.items()
            if key in LIST_SERIALIZER_KWARGS
        })
        meta = getattr(cls, 'Meta', None)
        list_serializer_class = getattr(meta, 'list_serializer_class', serializers.ListSerializer)

        return list_serializer_class(*args, **list_kwargs)

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        assert self.serializer_class is not None, (
                "'%s' should either include a `get_serializer_class` attribute, "
                "or override the `get_serializer()` method."
                % self.__class__.__name__
        )

        if isinstance(self.serializer_class, str):
            self.serializer_class = import_string(self.serializer_class)

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

    def to_internal_value(self, data):
        """
        Convierte el objeto serializado en un objeto interno.
        """
        return self.get_serializer().to_internal_value(data)

    def to_representation(self, instance):
        """
        Retorna la representación del objeto serializado.
        """
        model = self.get_serializer_class().Meta.model

        # Si el objeto no es una instancia del modelo (pk), lo obtenemos.
        if not isinstance(instance, model):
            pk_name = model._meta.pk.name
            instance = model.objects.get(**{pk_name: instance})

        return self.get_serializer().to_representation(instance)
