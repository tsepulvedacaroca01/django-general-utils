from functools import partialmethod
from typing import get_type_hints

from django.db import models
from django.db.models import Case, When, Value, BooleanField, TextField
from django.db.models.base import ModelBase
from django.db.models.functions import Now
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from ordered_model.models import OrderedModel
from queryable_properties.properties import queryable_property
from safedelete import SOFT_DELETE_CASCADE
from safedelete.config import FIELD_NAME
from safedelete.models import SafeDeleteModel

from .managers.base import BaseModelManager
from .querysets.base import BaseModelQuerySet
from .simple_history import HistoricalRecords
from .uuid import UUIDModel
from ..models import fields
from ..models.constraints import UniqueConstraint
from ..utils import delete_cache
from ..utils.formats import format_currency, format_decimal
from ..utils.image.blur_img_to_base64 import blur_img_to_base64, DEFAULT_BLUR_CODE


def register_model_signals(app_name: str):
    from django.apps import apps

    app_config = apps.get_app_config(app_name)

    for _model in app_config.get_models():
        if issubclass(_model, BaseModel):
            for _signal in _model._signals:
                _signal.set_model(_model)
                _signal.register()

    return None


class SignalRegister:
    callback = None
    signal = None
    model = None

    def __init__(self, callback, signal, **kwargs):
        self.callback = callback
        self.signal = signal
        self.kwargs = kwargs

    def set_model(self, model):
        self.model = model

    def register(self):
        assert self.model is not None, _('Model is not set')

        self.signal.connect(self.callback, sender=self.model, **self.kwargs)


class ModelBaseMeta(ModelBase):
    def __new__(cls, name, bases, attrs):
        super_new = super().__new__

        if 'Meta' in attrs and getattr(attrs['Meta'], 'abstract', False):
            return super_new(cls, name, bases, attrs)

        if 'history' not in attrs:
            attrs['history'] = HistoricalRecords()

        if 'tracker' not in attrs:
            attrs['tracker'] = FieldTracker()

        Meta = attrs.get('Meta', None)
        signals = []

        if Meta is not None and hasattr(Meta, 'signals'):
            signals = Meta.signals
            del Meta.signals

        model_class = super_new(cls, name, bases, attrs)

        meta = model_class._meta
        key_cache = f'{model_class.__module__}.{model_class.__name__.lower()}'

        if not hasattr(meta, 'constraints'):
            meta.constraints = []

        cls._validate_related_fields(model_class, meta, attrs)
        cls._add_formated_number(model_class, attrs)
        cls._add_blur_fields(model_class)

        model_class.add_to_class('_signals', signals)
        model_class.add_to_class('KEY_CACHE', key_cache)

        return model_class

    @staticmethod
    def _validate_related_fields(model_class, meta, attrs) -> None:
        """
        VALIDA QUE LOS CAMPOS RELACIONADOS SEAN DE TIPO CORRECTO
        """
        for field_name, field in attrs.items():
            if isinstance(field, models.OneToOneField):
                if not isinstance(field, fields.OneToOneField):
                    raise TypeError(
                        _(f'Field "{field_name}" OneToOneField is not supported when inheriting from BaseModel. Use django_general_utils.models.fields.OneToOneField instead.')
                    )
                else:
                    meta.constraints.append(
                        UniqueConstraint(
                            prefix=model_class.__name__.lower(),
                            fields=[field_name],
                            violation_error_message={
                                field_name: _('Ya existe un registro con este valor.'),
                            },
                        )
                    )

            if isinstance(field, models.ForeignKey) and (not isinstance(field, (fields.ForeignKey, fields.OneToOneField))):
                raise TypeError(
                    _(f'Field "{field_name}" model.ForeignKey is not supported when inheriting from BaseModel. Use django_general_utils.models.fields.ForeignKey instead.')
                )

        return None

    @staticmethod
    def _add_blur_fields(model_class) -> None:
        """
        AGREGA LOS CAMPOS DE IMAGEN PARA AGREGAR SU VERSIÓN BORROSA
        @return:
        """
        fields = getattr(model_class, '_images_field_to_blur')
        suffix = getattr(model_class, '_suffix_blur_code')

        for _field in fields:
            model_class.add_to_class(
                f'{_field}_{suffix}',
                TextField(
                    editable=False,
                    default=DEFAULT_BLUR_CODE
                )
            )

        return None

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

class BaseModel(SafeDeleteModel, OrderedModel, UUIDModel, metaclass=ModelBaseMeta):
    __FORMAT_LOCALE__ = 'es_CL'
    KEY_CACHE = None
    _images_field_to_blur = []
    _queryable_property_params = {}
    _suffix_blur_code = 'blur_code'
    _safedelete_policy = SOFT_DELETE_CASCADE
    objects = BaseModelManager(BaseModelQuerySet)

    class Meta:
        abstract = True
        ordering = ('-id',)

    @classmethod
    def get_queryable_property_params(cls, key: str, default=None):
        """
        Get the filter to be used when querying queryable properties.
        """
        default = default or {}
        return cls._queryable_property_params.get(key, default)

    @classmethod
    def filter_queryable_property(cls, **kwargs):
        """
        Get the filter to be used when querying queryable properties.
        """
        cls._queryable_property_params = kwargs

    @queryable_property(annotation_based=True)
    @classmethod
    def is_deleted(cls) -> bool:
        # noinspection PyTypeChecker
        return Case(
            When(**{f'{FIELD_NAME}__lt': Now(), 'then': Value(True)}),
            default=Value(False),
            output_field=BooleanField()
        )

    def set_blur_image(self, field: str) -> None:
        """
        ASIGNA LA IMAGEN BORROSA A UN CAMPO DE IMAGEN
        """
        setattr(
            self,
            f'{field}_{self._suffix_blur_code}',
            blur_img_to_base64(getattr(self, field))
        )

        return None

    def save(self, **kwargs):
        keep_deleted = kwargs.pop('keep_deleted', False)
        full_clean = kwargs.pop('full_clean', True)

        if not keep_deleted:
            if getattr(self, FIELD_NAME) and self.pk:
                # if the object was undeleted, we need to reset the order
                self.order = self.get_ordering_queryset().get_next_order()

            setattr(self, FIELD_NAME, None)

        for _field in self._images_field_to_blur:
            self.set_blur_image(_field)

        if full_clean:
            self.full_clean()

        if hasattr(self, 'KEY_CACHE'):
            delete_cache(self.KEY_CACHE)

        super().save(keep_deleted, **kwargs)
