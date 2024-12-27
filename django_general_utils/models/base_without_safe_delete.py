from functools import partialmethod
from typing import get_type_hints

from django.db import models
from django.db.models.base import ModelBase
from django.utils.functional import cached_property
from model_utils import FieldTracker
from ordered_model.models import OrderedModel

from .managers.base_without_safe_delete import BaseWithoutSafeDeleteModelManager
from .uuid_v2 import UUIDModelV2
from ..utils.formats import format_currency, format_decimal


class ModelBaseWithOutSafeDeleteMeta(ModelBase):
    def __new__(cls, name, bases, attrs):
        super_new = super().__new__

        if 'Meta' in attrs and getattr(attrs['Meta'], 'abstract', False):
            return super_new(cls, name, bases, attrs)

        if 'tracker' not in attrs:
            attrs['tracker'] = FieldTracker()

        Meta = attrs.get('Meta', None)
        signals = []

        if Meta is not None and hasattr(Meta, 'signals'):
            signals = Meta.signals
            del Meta.signals

        model_class = super_new(cls, name, bases, attrs)

        meta = model_class._meta

        if not hasattr(meta, 'constraints'):
            meta.constraints = []

        cls._add_formated_number(model_class, attrs)

        model_class.add_to_class('_signals', signals)

        return model_class

    @staticmethod
    def _add_formated_number(model_class, attrs) -> None:
        """
        AGREGA LOS MÉTODOS PARA FORMATEAR LOS NÚMEROS
        @return:
        """
        locale = model_class.__FORMAT_LOCALE__

        def get_format_decimal(
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

        def get_format_currency(
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

        for _field_name, _field in attrs.items():
            _add_method = False
            _hint = None
            _func = None

            if isinstance(_field, (property,)):
                _func = _field.fget
            elif type(_field) is cached_property:
                _func = _field.func
            elif hasattr(_field, 'get_annotation') and callable(_field.get_annotation):
                _func = _field.get_annotation


            if _func is not None:
                try:
                    _add_method = issubclass(get_type_hints(_func).get('return'), (int, float))
                except (NameError, TypeError):
                    pass
            else:
                _add_method = isinstance(
                    _field,
                    (
                        models.FloatField,
                        models.IntegerField,
                        models.PositiveIntegerField,
                        models.PositiveBigIntegerField,
                        models.PositiveSmallIntegerField
                    )
                )

            if _add_method:
                setattr(
                    model_class,
                    'get_%s_format_decimal' % _field_name,
                    partialmethod(
                        get_format_decimal,
                        attr_name=_field_name,
                        locale=locale
                    ),
                    )

                setattr(
                    model_class,
                    'get_%s_format_currency' % _field_name,
                    partialmethod(
                        get_format_currency,
                        attr_name=_field_name,
                        locale=locale
                    ),
                    )

        return None

class BaseWithoutSafeDeleteModel(OrderedModel, UUIDModelV2, metaclass=ModelBaseWithOutSafeDeleteMeta):
    __FORMAT_LOCALE__ = 'es_CL'
    objects = BaseWithoutSafeDeleteModelManager()

    class Meta:
        abstract = True
        ordering = ('-id',)

    def save(self, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            self.full_clean()

        super().save(**kwargs)
