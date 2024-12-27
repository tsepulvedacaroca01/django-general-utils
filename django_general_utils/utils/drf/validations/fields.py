from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class MinMaxElementsValidator:
    code = 'min_max_element_list'
    error_message = _('La lista debe tener entre {min} y {max} elemento(s).')
    error_message_only_min = _('La lista debe tener al menos {min} elemento(s).')
    error_message_only_max = _('La lista debe tener como máximo {max} elemento(s).')
    requires_context = True

    def __init__(self, min: int = None, max: int = None, keys: list = None, required: bool = True):
        self.min = min
        self.max = max
        self.keys = keys
        self.required = required

        assert not keys is None, _('key es requerido.')
        assert not min is None or not max is None, _('min o max es requerido.')

    def __call__(self, value, serializer):
        for _key in self.keys:
            assert not _key not in serializer.fields, _('el campo %s no existe en el serializador.' % _key)

        is_partial = serializer.partial

        errors = {
            _key: []
            for _key in self.keys
        }

        for _key in self.keys:
            _key_from_source = getattr(serializer.fields[_key], 'source', _key)

            if not is_partial and serializer.fields[_key].required:
                assert not _key_from_source not in value, _('el campo %s no existe en el body.' % _key)

            if not _key_from_source in value:
                continue

            if self.min is not None and self.min > len(value[_key_from_source]):
                errors[_key].append(
                    self.error_message_only_min.format(min=self.min)
                )

            if self.max is not None and self.max < len(value[_key_from_source]):
                errors[_key].append(
                    self.error_message_only_max.format(max=self.max),
                )

        if any([len(_errors) > 0 for _errors in errors.values()]):
            raise serializers.ValidationError(
                errors,
                code=self.code
            )
