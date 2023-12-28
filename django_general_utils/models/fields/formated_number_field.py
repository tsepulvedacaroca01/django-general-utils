from functools import partialmethod

from django.db import models

from ...utils.formats import format_currency, format_decimal


class FormattedNumberField(models.Field):
    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)

        locale = 'es_CL'

        setattr(
            cls,
            'get_%s_format_decimal' % name,
            partialmethod(
                self._get_format_decimal,
                attr_name=name,
                locale=locale
            ),
            )

        setattr(
            cls,
            'get_%s_format_currency' % name,
            partialmethod(
                self._get_format_currency,
                attr_name=name,
                locale=locale
            ),
            )

    def _get_format_decimal(
            self,
            attr_name: str,
            locale: str = 'es_CL',
            **kwargs
    ) -> str:
        """
        Get format decimal
        @return:
        """
        value = getattr(self, attr_name)

        if value is None:
            return ''

        return format_decimal(
            value,
            locale=locale,
            **kwargs,
        )


    def _get_format_currency(
            self,
            attr_name: str,
            currency='CLP',
            locale: str = 'es_CL',
            **kwargs
    ) -> str:
        """
        Get format decimal
        @return:
        """
        value = getattr(self, attr_name)

        if value is None:
            return ''

        return format_currency(
            value,
            currency=currency,
            locale=locale,
            **kwargs,
        )
