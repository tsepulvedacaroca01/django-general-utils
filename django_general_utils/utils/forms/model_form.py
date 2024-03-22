from django import forms
from django.conf import settings

from django_general_utils.utils import str_to_boolean


class ModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ModelForm, self).__init__(*args, **kwargs)
        self.initial_from_data = self.get_initial_from_data()
        self._clean_number()

    def get_initial_from_data(self):
        """
        @summary: Get initial data from request data
        @return:
        """
        prefix = self.prefix or ''

        if prefix != '':
            prefix = f'{prefix}-'

        fields = [
            f'{prefix}{_field}' for _field in self.fields
        ]

        return {
            _field.replace(f'{prefix}', '', 1): str_to_boolean(self.data.get(_field, ''), return_value=True)
            for _field in fields
        } | self.initial

    def _clean_number(self) -> None:
        """
        @summary: Clean number
        @return:
        """
        # if not settings.USE_THOUSAND_SEPARATOR:
        #     return

        prefix = self.prefix or ''
        self.data = self.data.copy()

        if prefix != '':
            prefix = f'{prefix}-'

        for _field in self.fields:
            _field_with_prefix = f'{prefix}{_field}'

            if _field_with_prefix not in self.data:
                continue

            _classes = self.base_fields[_field].widget.attrs.get('class', '')

            if settings.LOCAL_NUMBER_CLASS in _classes:
                self.data[_field_with_prefix] = (self.data[_field_with_prefix]
                                                 .replace(settings.THOUSAND_SEPARATOR, '')
                                                 .replace(settings.DECIMAL_SEPARATOR, '.'))

        return None
