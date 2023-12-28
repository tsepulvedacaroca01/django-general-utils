from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError


class MinMaxElementsValidator:
    code = 'min_max_element_list'
    error_message = _('La lista debe tener entre {min} y {max} elementos.')
    error_message_only_min = _('La lista debe tener al menos {min} elementos.')
    error_message_only_max = _('La lista debe tener como máximo {max} elementos.')

    def __init__(self, min: int = None, max: int = None, keys: list = None):
        self.min = min
        self.max = max
        self.keys = keys

        assert not keys is None, _('key es requerido.')
        assert not min is None or not max is None, _('min o max es requerido.')

    def __call__(self, value):
        for _key in self.keys:
            assert not _key not in value, _('key no existe en el diccionario.')

            if self.min is not None and self.min > len(value[_key]):
                raise ValidationError(
                    self.error_message_only_min.format(min=self.min),
                    code=self.code
                )

            if self.max is not None and self.max < len(value[_key]):
                raise ValidationError(
                    self.error_message_only_max.format(max=self.max),
                    code=self.code
                )
